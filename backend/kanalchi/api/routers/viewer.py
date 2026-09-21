"""Public viewer API on tenant hosts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db, require_tenant
from kanalchi.api.serializers import attach_media_links, post_out
from kanalchi.core.models import Channel, Post, Tenant

router = APIRouter(prefix="/api", tags=["viewer"])


async def _channel(db: AsyncSession, tenant: Tenant) -> Channel | None:
    return await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))


@router.get("/tenant")
async def tenant_info(tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)) -> dict:
    channel = await _channel(db, tenant)
    post_count = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
    )
    return {
        "id": tenant.id,
        "slug": tenant.slug,
        "domain": tenant.domain,
        "status": tenant.status,
        "title": tenant.title or (channel.title if channel else ""),
        "about": channel.about if channel else None,
        "username": channel.username if channel else None,
        "photo_url": f"/media/{channel.photo_key}" if channel and channel.photo_key else None,
        "participants_count": channel.participants_count if channel else None,
        "primary_lang": tenant.primary_lang,
        "locales": tenant.locales,
        "bot_username": tenant.bot_username,
        "post_count": post_count or 0,
        "theme": (tenant.settings or {}).get("theme", {}),
    }


def _decode_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    if not cursor:
        return None
    try:
        d, i = cursor.rsplit("_", 1)
        return datetime.fromisoformat(d), int(i)
    except ValueError as exc:
        raise HTTPException(400, "bad cursor") from exc


@router.get("/posts")
async def list_posts(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    channel = await _channel(db, tenant)
    if channel is None:
        return {"items": [], "next_cursor": None}
    q = select(Post).where(
        Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True)
    )
    c = _decode_cursor(cursor)
    if c:
        q = q.where((Post.date < c[0]) | ((Post.date == c[0]) & (Post.id < c[1])))
    rows = (await db.scalars(q.order_by(Post.date.desc(), Post.id.desc()).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    media_by, links_by = await attach_media_links(db, rows)
    items = [post_out(p, channel, media_by.get(p.id, []), links_by.get(p.id, [])) for p in rows]
    next_cursor = f"{rows[-1].date.isoformat()}_{rows[-1].id}" if has_more and rows else None
    return {"items": items, "next_cursor": next_cursor}


@router.get("/posts/top")
async def top_posts(
    metric: str = Query("views", pattern="^(views|forwards|reactions|engagement)$"),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(20, ge=1, le=50),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    channel = await _channel(db, tenant)
    if channel is None:
        return {"items": []}
    col = {
        "views": Post.views,
        "forwards": Post.forwards,
        "reactions": Post.reactions_total,
        "engagement": Post.engagement_score,
    }[metric]
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await db.scalars(
            select(Post)
            .where(
                Post.tenant_id == tenant.id,
                Post.is_deleted.is_(False),
                Post.is_album_root.is_(True),
                Post.date >= since,
            )
            .order_by(col.desc(), Post.date.desc())
            .limit(limit)
        )
    ).all()
    media_by, links_by = await attach_media_links(db, rows)
    return {"items": [post_out(p, channel, media_by.get(p.id, []), links_by.get(p.id, [])) for p in rows]}


@router.get("/posts/{tg_message_id}")
async def get_post(
    tg_message_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    channel = await _channel(db, tenant)
    if channel is None:
        raise HTTPException(404, "post not found")
    p = await db.scalar(
        select(Post).where(Post.channel_id == channel.id, Post.tg_message_id == tg_message_id)
    )
    if p is None or p.is_deleted:
        raise HTTPException(404, "post not found")
    if not p.is_album_root and p.grouped_id:
        root = await db.scalar(
            select(Post).where(
                Post.channel_id == channel.id, Post.grouped_id == p.grouped_id, Post.is_album_root.is_(True)
            )
        )
        p = root or p
    media_by, links_by = await attach_media_links(db, [p])
    prev_post = await db.scalar(
        select(Post.tg_message_id)
        .where(
            Post.channel_id == channel.id,
            Post.is_deleted.is_(False),
            Post.is_album_root.is_(True),
            Post.date < p.date,
        )
        .order_by(Post.date.desc())
        .limit(1)
    )
    next_post = await db.scalar(
        select(Post.tg_message_id)
        .where(
            Post.channel_id == channel.id,
            Post.is_deleted.is_(False),
            Post.is_album_root.is_(True),
            Post.date > p.date,
        )
        .order_by(Post.date.asc())
        .limit(1)
    )
    out = post_out(p, channel, media_by.get(p.id, []), links_by.get(p.id, []), full=True)
    out["prev_id"] = prev_post
    out["next_id"] = next_post
    return out
