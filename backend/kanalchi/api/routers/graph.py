"""The map: one window of posts, the tags they share, and the posts they point at.

A graph of the whole archive is a hairball at twelve thousand posts, so the map
is always drawn for a date window and the window is the reader's main control.
One payload serves every mode of the page: the post-and-tag constellation and
the tag-only map both derive from the same posts, tag list and edges, and the
tag co-occurrence the tag map needs is cheap enough to count in the browser.

Edges between posts come from two places Telegram already records: a post that
was written as a reply, and a post whose text links to another post of the same
channel (`t.me/<username>/<n>`). Both are kept only when the other end is in the
window, since an edge to a post that is not drawn is not an edge.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db, require_tenant
from kanalchi.core.models import Channel, Dimension, Post, PostLink, PostTag, Tag, Tenant
from kanalchi.core.repo import scoped

router = APIRouter(prefix="/api", tags=["graph"])

# How a post was filed rather than what it is about; these never make a useful node.
FILING_DIMENSIONS = frozenset(
    {"link_domains", "hashtags", "format", "stance", "language", "media_type", "dates"}
)
DEFAULT_WINDOW_DAYS = 90
MAX_POSTS = 3000
TITLE_CHARS = 90


def _title(post: Post) -> str:
    if post.title:
        return post.title
    first = post.text.strip().split("\n", 1)[0].strip()
    return first[:TITLE_CHARS] if len(first) <= TITLE_CHARS else first[: TITLE_CHARS - 1].rstrip() + "…"


def own_post_ids(urls: list[str], username: str | None) -> list[int]:
    """Message ids of links into the channel itself, e.g. `https://t.me/bakiroo/608` → 608."""
    if not username:
        return []
    pattern = re.compile(rf"^https?://(?:www\.)?t\.me/{re.escape(username)}/(\d+)(?:[/?#]|$)", re.IGNORECASE)
    out: list[int] = []
    for url in urls:
        m = pattern.match(url.strip())
        if m:
            out.append(int(m.group(1)))
    return out


@router.get("/graph")
async def graph(
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    limit: int = Query(MAX_POSTS, ge=50, le=MAX_POSTS),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
    end_day = to or datetime.now(UTC).date()
    start_day = from_ or end_day - timedelta(days=DEFAULT_WINDOW_DAYS)
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    start = datetime.combine(start_day, time.min, tzinfo=UTC)
    end = datetime.combine(end_day, time.max, tzinfo=UTC)
    # Posts per month over the whole archive, for the range picker under the map:
    # the reader chooses a window by the shape of the archive, not by typing dates.
    month = func.to_char(Post.date, "YYYY-MM").label("month")
    month_rows = (
        await db.execute(
            select(month, func.count())
            .where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
            .group_by(month)
            .order_by(month)
        )
    ).all()
    months = [{"month": m, "count": c} for m, c in month_rows]
    empty = {
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "truncated": False,
        "posts": [],
        "tags": [],
        "months": months,
    }
    if channel is None:
        return empty

    rows = (
        await db.scalars(
            scoped(Post, tenant.id)
            .where(
                Post.is_deleted.is_(False), Post.is_album_root.is_(True), Post.date >= start, Post.date <= end
            )
            .order_by(Post.date.desc(), Post.id.desc())
            .limit(limit + 1)
        )
    ).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    if not rows:
        return empty
    by_pk = {p.id: p for p in rows}
    in_window = {p.tg_message_id for p in rows}

    # Tags, indexed once and referenced from posts by position: a slug repeated on
    # five hundred posts is the bulk of the payload otherwise.
    tag_rows = (
        await db.execute(
            select(PostTag.post_id, Tag, Dimension.key)
            .join(Tag, Tag.id == PostTag.tag_id)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(
                PostTag.post_id.in_(by_pk.keys()),
                PostTag.tenant_id == tenant.id,
                Tag.status == "active",
                Dimension.is_visible.is_(True),
                Dimension.key.not_in(FILING_DIMENSIONS),
            )
        )
    ).all()
    tags: dict[str, dict[str, Any]] = {}
    post_tags: dict[int, list[str]] = {}
    for post_pk, tag, dimension in tag_rows:
        entry = tags.get(tag.slug)
        if entry is None:
            entry = tags[tag.slug] = {
                "slug": tag.slug,
                "name": tag.canonical_name,
                "labels": tag.labels or {},
                "dimension": dimension,
                "post_count": tag.post_count,
                "count": 0,
            }
        entry["count"] += 1
        post_tags.setdefault(post_pk, []).append(tag.slug)
    ordered = sorted(tags.values(), key=lambda t: (-t["count"], t["slug"]))
    index = {t["slug"]: i for i, t in enumerate(ordered)}

    link_rows = (
        (
            await db.execute(
                select(PostLink.post_id, PostLink.url).where(
                    PostLink.post_id.in_(by_pk.keys()), PostLink.url.ilike(f"%t.me/{channel.username}/%")
                )
            )
        ).all()
        if channel.username
        else []
    )
    links_by: dict[int, set[int]] = {}
    for post_pk, url in link_rows:
        for target in own_post_ids([url], channel.username):
            if target in in_window and target != by_pk[post_pk].tg_message_id:
                links_by.setdefault(post_pk, set()).add(target)

    posts = [
        {
            "id": p.tg_message_id,
            "date": p.date.isoformat(),
            "title": _title(p),
            "views": p.views,
            "reply": p.reply_to_tg_message_id if p.reply_to_tg_message_id in in_window else None,
            "links": sorted(links_by.get(p.id, ())),
            "tags": sorted(index[s] for s in post_tags.get(p.id, ())),
        }
        for p in rows
    ]
    return {
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "truncated": truncated,
        "posts": posts,
        "tags": ordered,
        "months": months,
    }
