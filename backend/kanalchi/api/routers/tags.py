"""Public tag browsing and search on tenant hosts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db, require_tenant
from kanalchi.api.serializers import attach_media_links, attach_tags, post_out
from kanalchi.core.models import Channel, Dimension, Post, PostTag, Tag, Tenant
from kanalchi.search import hybrid

router = APIRouter(prefix="/api", tags=["tags"])


def tag_out(tag: Tag, dimension_key: str | None = None) -> dict[str, Any]:
    return {
        "slug": tag.slug,
        "name": tag.canonical_name,
        "labels": tag.labels or {},
        "description": tag.description,
        "dimension": dimension_key,
        "post_count": tag.post_count,
        "engagement_score": round(tag.engagement_score or 0, 2),
        "parent_id": tag.parent_id,
    }


async def _channel(db: AsyncSession, tenant: Tenant) -> Channel | None:
    return await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))


async def _posts_by_ids(db: AsyncSession, tenant: Tenant, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    channel = await _channel(db, tenant)
    if channel is None:
        return []
    rows = (await db.scalars(select(Post).where(Post.id.in_(ids)))).all()
    by_id = {p.id: p for p in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    media_by, links_by = await attach_media_links(db, ordered)
    tags_by = await attach_tags(db, ordered)
    return [
        post_out(p, channel, media_by.get(p.id, []), links_by.get(p.id, []), tags_by.get(p.id, []))
        for p in ordered
    ]


@router.get("/dimensions")
async def list_dimensions(
    tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = (
        await db.execute(
            select(Dimension, func.count(Tag.id))
            .outerjoin(
                Tag, (Tag.dimension_id == Dimension.id) & (Tag.status == "active") & (Tag.post_count > 0)
            )
            .where(Dimension.tenant_id == tenant.id, Dimension.is_visible.is_(True))
            .group_by(Dimension.id)
            .order_by(Dimension.sort_order)
        )
    ).all()
    return [
        {
            "key": d.key,
            "labels": d.labels or {},
            "description": d.description,
            "kind": d.kind,
            "tag_count": count,
        }
        for d, count in rows
        if count
    ]


@router.get("/tags")
async def list_tags(
    dimension: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(Tag, Dimension.key)
        .join(Dimension, Dimension.id == Tag.dimension_id)
        .where(
            Tag.tenant_id == tenant.id,
            Tag.status == "active",
            Tag.post_count > 0,
            Dimension.is_visible.is_(True),
        )
    )
    if dimension:
        stmt = stmt.where(Dimension.key == dimension)
    if q:
        from kanalchi.text.normalize import normalize

        stmt = stmt.where(Tag.canonical_norm.like(f"%{normalize(q)}%"))
    rows = (await db.execute(stmt.order_by(Tag.post_count.desc()).limit(limit))).all()
    return [tag_out(t, key) for t, key in rows]


@router.get("/tags/{slug}")
async def tag_detail(
    slug: str,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            select(Tag, Dimension.key)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(Tag.tenant_id == tenant.id, Tag.slug == slug)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "tag not found")
    tag, dimension_key = row
    if tag.status == "merged" and tag.merged_into_id:
        target = await db.get(Tag, tag.merged_into_id)
        if target is not None:
            return {"redirect_to": target.slug}

    histogram = (
        await db.execute(
            text(
                """
                SELECT to_char(date_trunc('month', p.date), 'YYYY-MM') AS bucket, count(*) AS cnt
                FROM post_tags pt JOIN posts p ON p.id = pt.post_id
                WHERE pt.tag_id = :tag_id AND p.is_deleted = false
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"tag_id": tag.id},
        )
    ).all()
    co_tags = (
        await db.execute(
            text(
                """
                SELECT t.slug, t.canonical_name, t.labels, d.key AS dimension, count(*) AS cnt
                FROM post_tags a
                JOIN post_tags b ON b.post_id = a.post_id AND b.tag_id <> a.tag_id
                JOIN tags t ON t.id = b.tag_id AND t.status = 'active'
                LEFT JOIN dimensions d ON d.id = t.dimension_id
                WHERE a.tag_id = :tag_id
                GROUP BY t.slug, t.canonical_name, t.labels, d.key
                ORDER BY cnt DESC LIMIT 12
                """
            ),
            {"tag_id": tag.id},
        )
    ).all()
    span = (
        await db.execute(
            select(func.min(Post.date), func.max(Post.date))
            .join(PostTag, PostTag.post_id == Post.id)
            .where(PostTag.tag_id == tag.id, Post.is_deleted.is_(False))
        )
    ).first()
    children = (
        await db.scalars(
            select(Tag).where(Tag.parent_id == tag.id, Tag.status == "active").order_by(Tag.post_count.desc())
        )
    ).all()
    parent = await db.get(Tag, tag.parent_id) if tag.parent_id else None

    return {
        **tag_out(tag, dimension_key),
        "first_post_at": span[0] if span else None,
        "last_post_at": span[1] if span else None,
        "histogram": [{"month": b, "count": c} for b, c in histogram],
        "co_tags": [
            {"slug": s, "name": n, "labels": lb or {}, "dimension": dim, "count": c}
            for s, n, lb, dim, c in co_tags
        ],
        "children": [tag_out(c, dimension_key) for c in children],
        "parent": tag_out(parent, dimension_key) if parent else None,
    }


@router.get("/search")
async def search(
    q: str | None = None,
    tags: list[str] | None = Query(default=None),
    media_kind: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = Query("relevance", pattern="^(relevance|newest|oldest|views|reactions)$"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1000),
    with_facets: bool = True,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    hits = await hybrid.search(
        tenant.id,
        q,
        tag_slugs=tags or [],
        date_from=date_from,
        date_to=date_to,
        media_kind=media_kind,
        sort=sort,  # type: ignore[arg-type]
        limit=limit,
        offset=offset,
    )
    ids = [h[0] for h in hits]
    items = await _posts_by_ids(db, tenant, ids)
    out: dict[str, Any] = {
        "items": items,
        "count": len(items),
        "offset": offset,
        "has_more": len(items) == limit,
    }
    if with_facets:
        out["facets"] = await hybrid.facets(tenant.id, ids)
    return out


@router.get("/posts/{tg_message_id}/related")
async def related_posts(
    tg_message_id: int,
    limit: int = Query(5, ge=1, le=10),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    channel = await _channel(db, tenant)
    if channel is None:
        return {"items": []}
    post_id = await db.scalar(
        select(Post.id).where(Post.channel_id == channel.id, Post.tg_message_id == tg_message_id)
    )
    if post_id is None:
        return {"items": []}
    ids = await hybrid.related(tenant.id, post_id, limit=limit)
    return {"items": await _posts_by_ids(db, tenant, ids)}


@router.get("/posts/{tg_message_id}/tags")
async def post_tags(
    tg_message_id: int,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    channel = await _channel(db, tenant)
    if channel is None:
        return []
    post = await db.scalar(
        select(Post).where(Post.channel_id == channel.id, Post.tg_message_id == tg_message_id)
    )
    if post is None:
        return []
    post_id = post.id
    if not post.is_album_root and post.grouped_id:
        root = await db.scalar(
            select(Post.id).where(
                Post.channel_id == channel.id,
                Post.grouped_id == post.grouped_id,
                Post.is_album_root.is_(True),
            )
        )
        post_id = root or post_id
    rows = (
        await db.execute(
            select(Tag, Dimension.key, PostTag.confidence)
            .join(PostTag, PostTag.tag_id == Tag.id)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(PostTag.post_id == post_id, Tag.status == "active", Dimension.is_visible.is_(True))
            .order_by(Dimension.sort_order, Tag.post_count.desc())
        )
    ).all()
    return [{**tag_out(t, key), "confidence": round(conf or 1.0, 2)} for t, key, conf in rows]


@router.get("/stats")
async def stats(tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)) -> dict:
    """Channel-level numbers for the stats page."""
    totals = (
        await db.execute(
            select(
                func.count(Post.id),
                func.coalesce(func.sum(Post.views), 0),
                func.coalesce(func.avg(Post.views), 0),
                func.min(Post.date),
                func.max(Post.date),
            ).where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
        )
    ).first()
    by_month = (
        await db.execute(
            text(
                """
                SELECT to_char(date_trunc('month', date), 'YYYY-MM') AS bucket,
                       count(*) AS posts, coalesce(avg(views), 0)::int AS mean_views
                FROM posts
                WHERE tenant_id = :tenant_id AND is_deleted = false AND is_album_root = true
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"tenant_id": tenant.id},
        )
    ).all()
    top_tags = (
        await db.execute(
            select(Tag, Dimension.key)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(
                Tag.tenant_id == tenant.id,
                Tag.status == "active",
                Dimension.key.in_(["themes", "people", "gov_orgs"]),
            )
            .order_by(Tag.post_count.desc())
            .limit(20)
        )
    ).all()
    # Everything clock-shaped is computed in the channel's own timezone: a post
    # at 02:00 UTC is a 7 a.m. post in Tashkent, and that is the fact a reader wants.
    tz = (tenant.settings or {}).get("timezone") or "Asia/Tashkent"
    scope = "tenant_id = :tenant_id AND is_deleted = false AND is_album_root = true"
    params = {"tenant_id": tenant.id, "tz": tz}

    async def rows(sql: str):
        return (await db.execute(text(sql), params)).all()

    by_weekday = await rows(
        f"""SELECT extract(isodow FROM (date AT TIME ZONE :tz))::int AS dow,
                   count(*) AS posts, coalesce(avg(views), 0)::int AS mean_views
            FROM posts WHERE {scope} GROUP BY 1 ORDER BY 1"""
    )
    by_hour = await rows(
        f"""SELECT extract(hour FROM (date AT TIME ZONE :tz))::int AS hour,
                   count(*) AS posts, coalesce(avg(views), 0)::int AS mean_views
            FROM posts WHERE {scope} GROUP BY 1 ORDER BY 1"""
    )
    by_day = await rows(
        f"""SELECT to_char((date AT TIME ZONE :tz)::date, 'YYYY-MM-DD') AS day, count(*) AS posts
            FROM posts WHERE {scope} GROUP BY 1 ORDER BY 1"""
    )
    by_year = await rows(
        f"""SELECT extract(year FROM (date AT TIME ZONE :tz))::int AS year, count(*) AS posts,
                   coalesce(avg(views), 0)::int AS mean_views, coalesce(sum(views), 0)::bigint AS total_views
            FROM posts WHERE {scope} GROUP BY 1 ORDER BY 1"""
    )
    media_mix = await rows(
        f"""SELECT coalesce(media_kind, 'none') AS kind, count(*) AS posts
            FROM posts WHERE {scope} GROUP BY 1 ORDER BY 2 DESC"""
    )
    length_buckets = await rows(
        f"""SELECT CASE
                     WHEN length(coalesce(text, '')) < 200 THEN 'short'
                     WHEN length(coalesce(text, '')) < 800 THEN 'medium'
                     WHEN length(coalesce(text, '')) < 2000 THEN 'long'
                     ELSE 'essay' END AS bucket,
                   count(*) AS posts, coalesce(avg(views), 0)::int AS mean_views
            FROM posts WHERE {scope} GROUP BY 1"""
    )
    extra = (
        await db.execute(
            select(
                func.coalesce(func.sum(Post.forwards), 0),
                func.coalesce(func.sum(Post.reactions_total), 0),
                func.coalesce(func.avg(func.length(Post.text)), 0),
            ).where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
        )
    ).first()
    by_language = await rows(
        f"""SELECT language, count(*) AS posts FROM posts
            WHERE {scope} AND language IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""
    )

    # The longest run of consecutive posting days, straight from the daily counts.
    longest_streak = streak = 0
    previous = None
    for day, _ in by_day:
        current = datetime.strptime(day, "%Y-%m-%d").date()
        streak = streak + 1 if previous and (current - previous).days == 1 else 1
        longest_streak = max(longest_streak, streak)
        previous = current
    busiest = max(by_day, key=lambda r: r[1]) if by_day else None

    # --- Numbers that only exist once the archive has been read -----------
    # A follower-count service can tell you how often a channel posts. It cannot
    # tell you who the channel keeps naming, or what it quietly stopped covering.
    indexed_posts = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.tenant_id == tenant.id, Post.index_status.in_(["tagged", "extracted"]))
    )

    by_weekday_hour = await rows(
        f"""SELECT extract(isodow FROM (date AT TIME ZONE :tz))::int AS dow,
                   extract(hour FROM (date AT TIME ZONE :tz))::int AS hour,
                   count(*) AS posts
            FROM posts WHERE {scope} GROUP BY 1, 2"""
    )
    by_domain = await rows(
        """SELECT domain, count(*) AS links, count(DISTINCT post_id) AS posts
           FROM post_links WHERE tenant_id = :tenant_id AND domain IS NOT NULL
           GROUP BY 1 ORDER BY 2 DESC LIMIT 12"""
    )

    async def top_of(dimension: str, limit: int = 10):
        return (
            await db.execute(
                select(Tag.slug, Tag.canonical_name, Tag.labels, Tag.post_count)
                .join(Dimension, Dimension.id == Tag.dimension_id)
                .where(
                    Tag.tenant_id == tenant.id,
                    Tag.status == "active",
                    Tag.post_count > 0,
                    Dimension.key == dimension,
                )
                .order_by(Tag.post_count.desc())
                .limit(limit)
            )
        ).all()

    def tag_rows(raw):
        return [{"slug": sl, "name": n, "labels": lb or {}, "posts": c} for sl, n, lb, c in raw]

    themes_over_time = await rows(
        """SELECT to_char(date_trunc('quarter', p.date), 'YYYY-"Q"Q') AS quarter,
                  t.slug, t.canonical_name, t.labels, count(*) AS posts
           FROM post_tags pt
           JOIN posts p ON p.id = pt.post_id AND p.is_deleted = false AND p.is_album_root = true
           JOIN tags t ON t.id = pt.tag_id AND t.status = 'active'
           JOIN dimensions d ON d.id = t.dimension_id AND d.key = 'themes'
           WHERE pt.tenant_id = :tenant_id
             AND t.id IN (
               SELECT tg.id FROM tags tg JOIN dimensions dd ON dd.id = tg.dimension_id
               WHERE tg.tenant_id = :tenant_id AND dd.key = 'themes' AND tg.status = 'active'
               ORDER BY tg.post_count DESC LIMIT 6)
           GROUP BY 1, 2, 3, 4 ORDER BY 1"""
    )

    order = {"short": 0, "medium": 1, "long": 2, "essay": 3}
    return {
        "posts": totals[0] if totals else 0,
        "total_views": int(totals[1] or 0) if totals else 0,
        "mean_views": int(totals[2] or 0) if totals else 0,
        "total_forwards": int(extra[0] or 0) if extra else 0,
        "total_reactions": int(extra[1] or 0) if extra else 0,
        "mean_length": int(extra[2] or 0) if extra else 0,
        "first_post_at": totals[3] if totals else None,
        "last_post_at": totals[4] if totals else None,
        "timezone": tz,
        "by_month": [{"month": b, "posts": p, "mean_views": v} for b, p, v in by_month],
        "by_weekday": [{"dow": d, "posts": p, "mean_views": v} for d, p, v in by_weekday],
        "by_hour": [{"hour": h, "posts": p, "mean_views": v} for h, p, v in by_hour],
        "by_day": [{"day": d, "posts": p} for d, p in by_day],
        "by_year": [
            {"year": y, "posts": p, "mean_views": v, "total_views": int(t)} for y, p, v, t in by_year
        ],
        "media_mix": [{"kind": k, "posts": p} for k, p in media_mix],
        "by_length": sorted(
            ({"bucket": b, "posts": p, "mean_views": v} for b, p, v in length_buckets),
            key=lambda r: order[r["bucket"]],
        ),
        "by_language": [{"language": lang, "posts": p} for lang, p in by_language],
        "by_weekday_hour": [{"dow": d, "hour": h, "posts": p} for d, h, p in by_weekday_hour],
        "by_domain": [{"domain": d, "links": lk, "posts": p} for d, lk, p in by_domain],
        "indexed_posts": indexed_posts or 0,
        "top_themes": tag_rows(await top_of("themes")),
        "top_people": tag_rows(await top_of("people")),
        "top_gov_orgs": tag_rows(await top_of("gov_orgs")),
        "by_format": tag_rows(await top_of("format", 8)),
        "by_stance": tag_rows(await top_of("stance", 6)),
        "themes_over_time": [
            {"quarter": q, "slug": sl, "name": n, "labels": lb or {}, "posts": c}
            for q, sl, n, lb, c in themes_over_time
        ],
        "longest_streak_days": longest_streak,
        "busiest_day": {"day": busiest[0], "posts": busiest[1]} if busiest else None,
        "top_tags": [tag_out(t, key) for t, key in top_tags],
    }


@router.get("/stories")
async def list_stories(tenant: Tenant = Depends(require_tenant)) -> list[dict]:
    """Running stories: groups of posts the archive found by similarity, named by the assistant."""
    from kanalchi.ai.threads import thread_list

    return await thread_list(tenant.id)


@router.get("/stories/{slug}")
async def story_detail(
    slug: str, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    from kanalchi.core.models import Thread, ThreadPost

    thread = await db.scalar(select(Thread).where(Thread.tenant_id == tenant.id, Thread.slug == slug))
    if thread is None:
        raise HTTPException(404, "story not found")
    post_ids = (
        await db.scalars(
            select(ThreadPost.post_id)
            .join(Post, Post.id == ThreadPost.post_id)
            .where(ThreadPost.thread_id == thread.id)
            .order_by(Post.date)
        )
    ).all()
    return {
        "slug": thread.slug,
        "title": thread.title or {},
        "summary": thread.summary or {},
        "first_at": thread.first_at,
        "last_at": thread.last_at,
        "post_count": thread.post_count,
        "items": await _posts_by_ids(db, tenant, list(post_ids)),
    }


@router.get("/tags/{slug}/summary")
async def tag_summary(
    slug: str, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    """What the channel has said about this entity over time, if a summary has been generated."""
    from kanalchi.core.models import EntitySummary

    tag = await db.scalar(select(Tag).where(Tag.tenant_id == tenant.id, Tag.slug == slug))
    if tag is None:
        raise HTTPException(404, "tag not found")
    summary = await db.get(EntitySummary, tag.id)
    if summary is None:
        return {"available": False}
    return {
        "available": True,
        "summary": summary.summary or {},
        "citations": summary.citations or [],
        "generated_at": summary.generated_at,
        "is_stale": summary.is_stale,
    }
