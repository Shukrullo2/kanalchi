"""Story threads and entity summaries: the two things an archive can say that a single post cannot.

Threads are found without a model. Posts that are close in embedding space and close in time are
almost always the same running story, so a k-nearest-neighbour graph plus connected components finds
them for free; the model is only asked to name and summarise what the graph already grouped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text

from kanalchi.ai.claude import complete_json, system_blocks
from kanalchi.core.db import session_scope
from kanalchi.core.jobs import update_job_run
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, EntitySummary, Post, PostTag, Tag, Tenant, Thread, ThreadPost
from kanalchi.text.slug import slugify

log = get_logger(__name__)

NEIGHBOURS = 8
MIN_SIMILARITY = 0.80
MAX_GAP_DAYS = 120
MIN_THREAD_POSTS = 3
MAX_THREADS = 40
SUMMARY_MIN_POSTS = 5

# Nearest neighbours per post, restricted to a time window: two posts about the same subject a year
# apart are related, but they are not the same running story.
NEIGHBOUR_SQL = text(
    """
WITH post_vectors AS (
    SELECT c.post_id, p.date, c.embedding
    FROM post_chunks c
    JOIN posts p ON p.id = c.post_id AND p.is_deleted = false AND p.is_album_root = true
    WHERE c.tenant_id = :tenant_id AND c.position = 0 AND c.embedding IS NOT NULL
)
SELECT a.post_id AS left_id, b.post_id AS right_id, 1 - (a.embedding <=> b.embedding) AS similarity
FROM post_vectors a
CROSS JOIN LATERAL (
    SELECT v.post_id, v.embedding
    FROM post_vectors v
    WHERE v.post_id <> a.post_id
      AND v.date BETWEEN a.date - make_interval(days => :max_gap) AND a.date + make_interval(days => :max_gap)
    ORDER BY v.embedding <=> a.embedding
    LIMIT :k
) b
WHERE 1 - (a.embedding <=> b.embedding) >= :min_similarity
"""
)

THREAD_SYSTEM = """You name and summarise a running story in one Telegram channel.

You are given posts that the archive has already grouped together, in date order. Your job is to say
what the story is and how it developed, using only those posts.

- The title is a short noun phrase, not a sentence and not a headline with a verb.
- The summary is two or three sentences: what happened, how it changed over time, where it stands in
  the last post. Write it in the channel's own language for `uz`, plus Russian and English.
- Cite the post ids you relied on.
- If the posts do not actually form one story, say so in `notes` and give the group a plain descriptive title."""

ENTITY_SYSTEM = """You summarise what one Telegram channel has published about one subject.

You are given that channel's posts mentioning the subject, oldest first. Write what the channel has
said, in the order it said it, and note where its coverage or stance changed.

- Report the channel's claims as the channel's claims. Do not add facts from outside these posts.
- Two or three sentences per language: Uzbek (Latin), Russian, English.
- Cite the post ids that carry the key points."""


def _thread_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title_uz": {"type": "string"},
            "title_ru": {"type": "string"},
            "title_en": {"type": "string"},
            "summary_uz": {"type": "string"},
            "summary_ru": {"type": "string"},
            "summary_en": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "integer"}},
            "notes": {"type": "string"},
        },
        "required": [
            "title_uz",
            "title_ru",
            "title_en",
            "summary_uz",
            "summary_ru",
            "summary_en",
            "citations",
            "notes",
        ],
    }


def _summary_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_uz": {"type": "string"},
            "summary_ru": {"type": "string"},
            "summary_en": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["summary_uz", "summary_ru", "summary_en", "citations"],
    }


def _components(edges: list[tuple[int, int]]) -> list[set[int]]:
    """Union-find over the neighbour graph."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for left, right in edges:
        a, b = find(left), find(right)
        if a != b:
            parent[a] = b

    groups: dict[int, set[int]] = {}
    for node in parent:
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())


async def find_threads(tenant_id: int) -> list[list[int]]:
    """Groups of post ids that look like one running story. No model involved."""
    async with session_scope() as db:
        rows = (
            await db.execute(
                NEIGHBOUR_SQL,
                {
                    "tenant_id": tenant_id,
                    "k": NEIGHBOURS,
                    "min_similarity": MIN_SIMILARITY,
                    "max_gap": MAX_GAP_DAYS,
                },
            )
        ).all()
    groups = _components([(r[0], r[1]) for r in rows])
    sized = [g for g in groups if len(g) >= MIN_THREAD_POSTS]
    sized.sort(key=len, reverse=True)
    return [sorted(g) for g in sized[:MAX_THREADS]]


async def build_threads(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    groups = await find_threads(tenant_id)
    if not groups:
        return {"threads": 0}

    cost = 0.0
    built = 0
    async with session_scope() as db:
        await db.execute(
            delete(ThreadPost).where(
                ThreadPost.thread_id.in_(select(Thread.id).where(Thread.tenant_id == tenant_id))
            )
        )
        await db.execute(delete(Thread).where(Thread.tenant_id == tenant_id))

    for index, post_ids in enumerate(groups):
        async with session_scope() as db:
            posts = (await db.scalars(select(Post).where(Post.id.in_(post_ids)).order_by(Post.date))).all()
        if len(posts) < MIN_THREAD_POSTS:
            continue

        listing = "\n\n".join(
            f"[{p.tg_message_id}] {p.date.date().isoformat()}: {' '.join((p.text or '').split())[:600]}"
            for p in posts[:30]
        )
        result, call_cost = await complete_json(
            tenant_id=tenant_id,
            purpose="summary",
            system=system_blocks(THREAD_SYSTEM),
            user=f"Posts in this group ({len(posts)} total):\n\n{listing}",
            schema=_thread_schema(),
            effort="medium",
            max_tokens=4000,
        )
        cost += call_cost
        if result is None:
            continue

        async with session_scope() as db:
            thread = Thread(
                tenant_id=tenant_id,
                slug=f"{slugify(result['title_en'])[:70]}-{index + 1}",
                title={"uz": result["title_uz"], "ru": result["title_ru"], "en": result["title_en"]},
                summary={"uz": result["summary_uz"], "ru": result["summary_ru"], "en": result["summary_en"]},
                first_at=posts[0].date,
                last_at=posts[-1].date,
                post_count=len(posts),
                citations=[int(c) for c in (result.get("citations") or [])][:20],
            )
            db.add(thread)
            await db.flush()
            for p in posts:
                db.add(ThreadPost(thread_id=thread.id, post_id=p.id))
        built += 1
        await update_job_run(job_run_id, progress={"stage": "threads", "done": built, "total": len(groups)})

    log.info("threads.built", tenant_id=tenant_id, threads=built, cost=round(cost, 4))
    return {"threads": built, "cost_usd": cost}


async def stale_summary_tag_ids(tenant_id: int, limit: int = 25) -> list[int]:
    """Entities worth summarising: enough coverage to be interesting, and not already up to date."""
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Tag.id)
                .outerjoin(EntitySummary, EntitySummary.tag_id == Tag.id)
                .where(
                    Tag.tenant_id == tenant_id,
                    Tag.status == "active",
                    Tag.post_count >= SUMMARY_MIN_POSTS,
                    (EntitySummary.tag_id.is_(None)) | (EntitySummary.is_stale.is_(True)),
                )
                .order_by(Tag.post_count.desc())
                .limit(limit)
            )
        ).all()
    return [r[0] for r in rows]


async def build_entity_summary(tenant_id: int, tag_id: int) -> dict[str, Any]:
    async with session_scope() as db:
        tag = await db.get(Tag, tag_id)
        if tag is None or tag.tenant_id != tenant_id:
            return {"skipped": True}
        posts = (
            await db.scalars(
                select(Post)
                .join(PostTag, PostTag.post_id == Post.id)
                .where(PostTag.tag_id == tag_id, Post.is_deleted.is_(False))
                .order_by(Post.date)
                .limit(40)
            )
        ).all()
        name = tag.canonical_name
    if len(posts) < SUMMARY_MIN_POSTS:
        return {"skipped": "not enough posts"}

    listing = "\n\n".join(
        f"[{p.tg_message_id}] {p.date.date().isoformat()}: {' '.join((p.text or '').split())[:700]}"
        for p in posts
    )
    result, cost = await complete_json(
        tenant_id=tenant_id,
        purpose="summary",
        system=system_blocks(ENTITY_SYSTEM),
        user=f"Subject: {name}\n\nPosts mentioning it ({len(posts)}):\n\n{listing}",
        schema=_summary_schema(),
        effort="medium",
        max_tokens=4000,
    )
    if result is None:
        return {"failed": True, "cost_usd": cost}

    async with session_scope() as db:
        existing = await db.get(EntitySummary, tag_id)
        payload = {"uz": result["summary_uz"], "ru": result["summary_ru"], "en": result["summary_en"]}
        citations = [int(c) for c in (result.get("citations") or [])][:20]
        if existing is None:
            db.add(
                EntitySummary(
                    tenant_id=tenant_id,
                    tag_id=tag_id,
                    summary=payload,
                    citations=citations,
                    generated_at=datetime.now(UTC),
                    is_stale=False,
                    cost_usd=cost,
                )
            )
        else:
            existing.summary = payload
            existing.citations = citations
            existing.generated_at = datetime.now(UTC)
            existing.is_stale = False
            existing.cost_usd = cost
    return {"tag_id": tag_id, "cost_usd": cost}


async def mark_summaries_stale(tenant_id: int, since_hours: int = 26) -> int:
    """A summary goes stale when the tag picks up a post newer than the summary itself."""
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(EntitySummary.tag_id, func.max(Post.date))
                .join(PostTag, PostTag.tag_id == EntitySummary.tag_id)
                .join(Post, Post.id == PostTag.post_id)
                .where(EntitySummary.tenant_id == tenant_id, Post.is_deleted.is_(False))
                .group_by(EntitySummary.tag_id, EntitySummary.generated_at)
                .having(func.max(Post.date) > EntitySummary.generated_at)
            )
        ).all()
        stale = 0
        for tag_id, _ in rows:
            summary = await db.get(EntitySummary, tag_id)
            if summary is not None and not summary.is_stale:
                summary.is_stale = True
                stale += 1
    log.info("summaries.marked_stale", tenant_id=tenant_id, count=stale, cutoff=cutoff.isoformat())
    return stale


async def thread_list(tenant_id: int) -> list[dict[str, Any]]:
    async with session_scope() as db:
        rows = (
            await db.scalars(
                select(Thread).where(Thread.tenant_id == tenant_id).order_by(Thread.last_at.desc())
            )
        ).all()
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        tenant = await db.get(Tenant, tenant_id)
    return [
        {
            "slug": t.slug,
            "title": t.title or {},
            "summary": t.summary or {},
            "first_at": t.first_at,
            "last_at": t.last_at,
            "post_count": t.post_count,
            "citations": t.citations or [],
            "channel": channel.title if channel else (tenant.title if tenant else ""),
        }
        for t in rows
    ]
