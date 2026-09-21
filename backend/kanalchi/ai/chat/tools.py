"""Tools the chat model uses to read the archive.

Every tool returns compact JSON and, crucially, returns post ids. The agent loop records which ids
a tool actually surfaced this turn; any citation the model writes for an id it was never shown is
stripped before the answer reaches the reader. That is what keeps citations honest.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Dimension, Post, PostTag, Tag, Tenant
from kanalchi.search import hybrid

log = get_logger(__name__)

SNIPPET = 300
FULL_TEXT = 4000
MAX_POSTS = 5


def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _snippet(text_value: str, limit: int = SNIPPET) -> str:
    cleaned = " ".join((text_value or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rsplit(" ", 1)[0] + "…"


async def _post_rows(tenant_id: int, post_ids: list[int]) -> list[dict[str, Any]]:
    if not post_ids:
        return []
    async with session_scope() as db:
        rows = (await db.scalars(select(Post).where(Post.id.in_(post_ids)))).all()
        tag_rows = (
            await db.execute(
                select(PostTag.post_id, Tag.slug)
                .join(Tag, Tag.id == PostTag.tag_id)
                .where(PostTag.post_id.in_(post_ids), Tag.status == "active")
            )
        ).all()
    tags_by: dict[int, list[str]] = {}
    for pid, slug in tag_rows:
        tags_by.setdefault(pid, []).append(slug)
    by_id = {p.id: p for p in rows}
    out = []
    for pid in post_ids:
        p = by_id.get(pid)
        if p is None:
            continue
        out.append(
            {
                "post_id": p.tg_message_id,
                "date": p.date.date().isoformat(),
                "title": p.title,
                "snippet": _snippet(p.text),
                "views": p.views,
                "reactions": p.reactions_total,
                "tags": tags_by.get(p.id, [])[:10],
                "_internal_id": p.id,
            }
        )
    return out


# --------------------------------------------------------------------------- definitions
def tool_definitions(kind: str = "viewer") -> list[dict[str, Any]]:
    """JSON-schema tool definitions, sorted by name so the cached prompt prefix stays byte-stable."""
    common: list[dict[str, Any]] = [
        {
            "name": "channel_stats",
            "description": "Overall numbers for the channel: post count, date span, average views, busiest months.",
            "strict": True,
            "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
        {
            "name": "get_posts",
            "description": "Read the full text of specific posts by their post_id. Use after search to quote accurately.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "post_ids": {"type": "array", "items": {"type": "integer"}, "description": f"at most {MAX_POSTS} ids"}
                },
                "required": ["post_ids"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_tags",
            "description": "List the tags of one dimension (themes, people, gov_orgs, orgs, locations, ...).",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "dimension": {"type": ["string", "null"]},
                    "query": {"type": ["string", "null"], "description": "filter tags by name"},
                    "limit": {"type": "integer"},
                },
                "required": ["dimension", "query", "limit"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_posts",
            "description": (
                "Search the channel archive. Works across Uzbek Latin, Uzbek Cyrillic, Russian and English: "
                "a query in one script finds posts written in another. Returns post ids you can cite."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "tag slugs, all must match"},
                    "date_from": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "date_to": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "sort": {"type": "string", "enum": ["relevance", "newest", "oldest", "views", "reactions"]},
                    "limit": {"type": "integer"},
                },
                "required": ["query", "tags", "date_from", "date_to", "sort", "limit"],
                "additionalProperties": False,
            },
        },
        {
            "name": "tag_overview",
            "description": "Everything about one tag: how many posts, when it was covered, related tags, top posts.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
                "additionalProperties": False,
            },
        },
        {
            "name": "timeline",
            "description": "How coverage of a tag or query is distributed over time, with one example post per bucket.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "a tag slug or a free-text query"},
                    "kind": {"type": "string", "enum": ["tag", "query"]},
                    "granularity": {"type": "string", "enum": ["month", "quarter", "year"]},
                },
                "required": ["subject", "kind", "granularity"],
                "additionalProperties": False,
            },
        },
        {
            "name": "top_posts",
            "description": "The channel's most viewed, most reacted or most forwarded posts in a period.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["views", "reactions", "forwards", "engagement"]},
                    "days": {"type": "integer", "description": "look-back window, e.g. 30, 365, 3650"},
                    "tag": {"type": ["string", "null"], "description": "restrict to one tag slug"},
                    "limit": {"type": "integer"},
                },
                "required": ["metric", "days", "tag", "limit"],
                "additionalProperties": False,
            },
        },
    ]
    return sorted(common, key=lambda t: t["name"])


# --------------------------------------------------------------------------- implementations
class ToolBox:
    """Executes tool calls for one tenant and remembers which post ids it revealed."""

    def __init__(self, tenant_id: int, locale: str = "uz") -> None:
        self.tenant_id = tenant_id
        self.locale = locale
        self.seen_post_ids: set[int] = set()

    def _remember(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            self.seen_post_ids.add(int(row["post_id"]))
            row.pop("_internal_id", None)
        return rows

    async def run(self, name: str, args: dict[str, Any]) -> str:
        handler = getattr(self, f"_{name}", None)
        if handler is None:
            return _compact({"error": f"unknown tool {name}"})
        try:
            return await handler(args)
        except Exception as exc:  # noqa: BLE001
            log.warning("chat.tool_failed", tool=name, error=str(exc)[:300])
            return _compact({"error": f"{name} failed: {type(exc).__name__}"})

    # ---- search -----------------------------------------------------------
    async def _search_posts(self, args: dict[str, Any]) -> str:
        limit = max(1, min(int(args.get("limit") or 10), 10))
        hits = await hybrid.search(
            self.tenant_id,
            args.get("query"),
            tag_slugs=list(args.get("tags") or []),
            date_from=_parse_date(args.get("date_from")),
            date_to=_parse_date(args.get("date_to")),
            sort=args.get("sort") or "relevance",
            limit=limit,
        )
        rows = await _post_rows(self.tenant_id, [h[0] for h in hits])
        return _compact({"results": self._remember(rows), "count": len(rows)})

    async def _get_posts(self, args: dict[str, Any]) -> str:
        wanted = [int(i) for i in (args.get("post_ids") or [])][:MAX_POSTS]
        if not wanted:
            return _compact({"posts": []})
        async with session_scope() as db:
            channel = await db.scalar(select(Channel).where(Channel.tenant_id == self.tenant_id))
            if channel is None:
                return _compact({"posts": []})
            rows = (
                await db.scalars(
                    select(Post).where(Post.channel_id == channel.id, Post.tg_message_id.in_(wanted))
                )
            ).all()
            tag_rows = (
                await db.execute(
                    select(PostTag.post_id, Tag.slug)
                    .join(Tag, Tag.id == PostTag.tag_id)
                    .where(PostTag.post_id.in_([p.id for p in rows]), Tag.status == "active")
                )
            ).all()
        tags_by: dict[int, list[str]] = {}
        for pid, slug in tag_rows:
            tags_by.setdefault(pid, []).append(slug)
        posts = []
        for p in rows:
            self.seen_post_ids.add(p.tg_message_id)
            posts.append(
                {
                    "post_id": p.tg_message_id,
                    "date": p.date.isoformat(),
                    "text": (p.text or "")[:FULL_TEXT],
                    "title": p.title,
                    "summary": p.summary,
                    "views": p.views,
                    "reactions": p.reactions_total,
                    "forwards": p.forwards,
                    "media": p.media_kind,
                    "tags": tags_by.get(p.id, []),
                }
            )
        return _compact({"posts": posts})

    # ---- tags -------------------------------------------------------------
    async def _list_tags(self, args: dict[str, Any]) -> str:
        limit = max(1, min(int(args.get("limit") or 50), 200))
        stmt = (
            select(Tag.slug, Tag.canonical_name, Tag.post_count, Dimension.key)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(
                Tag.tenant_id == self.tenant_id,
                Tag.status == "active",
                Tag.post_count > 0,
                Dimension.is_visible.is_(True),
            )
        )
        if args.get("dimension"):
            stmt = stmt.where(Dimension.key == args["dimension"])
        if args.get("query"):
            from kanalchi.text.normalize import normalize

            stmt = stmt.where(Tag.canonical_norm.like(f"%{normalize(args['query'])}%"))
        async with session_scope() as db:
            rows = (await db.execute(stmt.order_by(Tag.post_count.desc()).limit(limit))).all()
        return _compact(
            {"tags": [{"slug": s, "name": n, "posts": c, "dimension": d} for s, n, c, d in rows]}
        )

    async def _tag_overview(self, args: dict[str, Any]) -> str:
        slug = args.get("slug") or ""
        async with session_scope() as db:
            row = (
                await db.execute(
                    select(Tag, Dimension.key)
                    .join(Dimension, Dimension.id == Tag.dimension_id)
                    .where(Tag.tenant_id == self.tenant_id, Tag.slug == slug)
                )
            ).first()
            if row is None:
                return _compact({"error": f"no tag with slug {slug}"})
            tag, dimension = row
            span = (
                await db.execute(
                    select(func.min(Post.date), func.max(Post.date))
                    .join(PostTag, PostTag.post_id == Post.id)
                    .where(PostTag.tag_id == tag.id, Post.is_deleted.is_(False))
                )
            ).first()
            months = (
                await db.execute(
                    text(
                        """
                        SELECT to_char(date_trunc('month', p.date), 'YYYY-MM') AS m, count(*) AS c
                        FROM post_tags pt JOIN posts p ON p.id = pt.post_id
                        WHERE pt.tag_id = :tag_id AND p.is_deleted = false
                        GROUP BY 1 ORDER BY 1
                        """
                    ),
                    {"tag_id": tag.id},
                )
            ).all()
            co = (
                await db.execute(
                    text(
                        """
                        SELECT t.slug, count(*) AS c
                        FROM post_tags a
                        JOIN post_tags b ON b.post_id = a.post_id AND b.tag_id <> a.tag_id
                        JOIN tags t ON t.id = b.tag_id AND t.status = 'active'
                        WHERE a.tag_id = :tag_id GROUP BY t.slug ORDER BY c DESC LIMIT 10
                        """
                    ),
                    {"tag_id": tag.id},
                )
            ).all()
            top_ids = (
                await db.scalars(
                    select(Post.id)
                    .join(PostTag, PostTag.post_id == Post.id)
                    .where(PostTag.tag_id == tag.id, Post.is_deleted.is_(False))
                    .order_by(Post.views.desc())
                    .limit(5)
                )
            ).all()
        rows = await _post_rows(self.tenant_id, list(top_ids))
        return _compact(
            {
                "slug": tag.slug,
                "name": tag.canonical_name,
                "dimension": dimension,
                "posts": tag.post_count,
                "first_post": span[0].date().isoformat() if span and span[0] else None,
                "last_post": span[1].date().isoformat() if span and span[1] else None,
                "reach_vs_average": round(tag.engagement_score or 0, 2),
                "by_month": [{"month": m, "posts": c} for m, c in months],
                "related_tags": [{"slug": s, "together": c} for s, c in co],
                "top_posts": self._remember(rows),
            }
        )

    # ---- aggregates -------------------------------------------------------
    async def _timeline(self, args: dict[str, Any]) -> str:
        subject = args.get("subject") or ""
        kind = args.get("kind") or "tag"
        granularity = args.get("granularity") or "month"
        trunc = {"month": "month", "quarter": "quarter", "year": "year"}[granularity]
        fmt = {"month": "YYYY-MM", "quarter": "YYYY-\"Q\"Q", "year": "YYYY"}[granularity]

        if kind == "tag":
            async with session_scope() as db:
                rows = (
                    await db.execute(
                        text(
                            f"""
                            SELECT to_char(date_trunc('{trunc}', p.date), '{fmt}') AS bucket,
                                   count(*) AS posts,
                                   (array_agg(p.id ORDER BY p.views DESC))[1] AS example
                            FROM post_tags pt
                            JOIN tags t ON t.id = pt.tag_id AND t.slug = :slug
                            JOIN posts p ON p.id = pt.post_id AND p.is_deleted = false
                            WHERE pt.tenant_id = :tenant_id
                            GROUP BY 1 ORDER BY 1
                            """
                        ),
                        {"slug": subject, "tenant_id": self.tenant_id},
                    )
                ).all()
        else:
            hits = await hybrid.search(self.tenant_id, subject, limit=50)
            ids = [h[0] for h in hits]
            if not ids:
                return _compact({"buckets": []})
            async with session_scope() as db:
                rows = (
                    await db.execute(
                        text(
                            f"""
                            SELECT to_char(date_trunc('{trunc}', date), '{fmt}') AS bucket,
                                   count(*) AS posts,
                                   (array_agg(id ORDER BY views DESC))[1] AS example
                            FROM posts WHERE id = ANY(:ids) GROUP BY 1 ORDER BY 1
                            """
                        ),
                        {"ids": ids},
                    )
                ).all()

        examples = await _post_rows(self.tenant_id, [r[2] for r in rows if r[2]])
        by_internal = {e["_internal_id"]: e["post_id"] for e in examples}
        self._remember(examples)
        return _compact(
            {
                "subject": subject,
                "buckets": [
                    {"period": b, "posts": c, "example_post_id": by_internal.get(ex)} for b, c, ex in rows
                ],
            }
        )

    async def _top_posts(self, args: dict[str, Any]) -> str:
        metric = args.get("metric") or "views"
        column = {
            "views": Post.views,
            "reactions": Post.reactions_total,
            "forwards": Post.forwards,
            "engagement": Post.engagement_score,
        }[metric]
        days = max(1, int(args.get("days") or 365))
        limit = max(1, min(int(args.get("limit") or 10), 20))
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(Post.id)
            .where(
                Post.tenant_id == self.tenant_id,
                Post.is_deleted.is_(False),
                Post.is_album_root.is_(True),
                Post.date >= since,
            )
            .order_by(column.desc())
            .limit(limit)
        )
        if args.get("tag"):
            stmt = stmt.join(PostTag, PostTag.post_id == Post.id).join(
                Tag, (Tag.id == PostTag.tag_id) & (Tag.slug == args["tag"])
            )
        async with session_scope() as db:
            ids = (await db.scalars(stmt)).all()
        rows = await _post_rows(self.tenant_id, list(ids))
        return _compact({"metric": metric, "days": days, "results": self._remember(rows)})

    async def _channel_stats(self, args: dict[str, Any]) -> str:
        async with session_scope() as db:
            tenant = await db.get(Tenant, self.tenant_id)
            channel = await db.scalar(select(Channel).where(Channel.tenant_id == self.tenant_id))
            totals = (
                await db.execute(
                    select(
                        func.count(Post.id),
                        func.coalesce(func.avg(Post.views), 0),
                        func.min(Post.date),
                        func.max(Post.date),
                    ).where(
                        Post.tenant_id == self.tenant_id,
                        Post.is_deleted.is_(False),
                        Post.is_album_root.is_(True),
                    )
                )
            ).first()
            busiest = (
                await db.execute(
                    text(
                        """
                        SELECT to_char(date_trunc('month', date), 'YYYY-MM') AS m, count(*) AS c
                        FROM posts WHERE tenant_id = :tenant_id AND is_deleted = false
                        GROUP BY 1 ORDER BY c DESC LIMIT 3
                        """
                    ),
                    {"tenant_id": self.tenant_id},
                )
            ).all()
        return _compact(
            {
                "channel": channel.title if channel else tenant.title,
                "subscribers": channel.participants_count if channel else None,
                "posts": totals[0] if totals else 0,
                "average_views": int(totals[1] or 0) if totals else 0,
                "first_post": totals[2].date().isoformat() if totals and totals[2] else None,
                "last_post": totals[3].date().isoformat() if totals and totals[3] else None,
                "busiest_months": [{"month": m, "posts": c} for m, c in busiest],
            }
        )


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
