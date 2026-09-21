"""JSON shapes for posts/media shared by viewer, studio and admin routes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.core.models import Channel, Media, Post, PostLink
from kanalchi.telegram.ingest import t_me_url


def media_out(m: Media) -> dict[str, Any]:
    return {
        "id": m.id,
        "kind": m.kind,
        "mime": m.mime,
        "width": m.width,
        "height": m.height,
        "duration_s": m.duration_s,
        "size_bytes": m.size_bytes,
        "file_name": m.file_name,
        "status": m.status,
        "url": f"/media/{m.object_key}" if m.object_key else None,
        "thumb_url": f"/media/{m.thumb_key}" if m.thumb_key else None,
        "external_url": m.external_url,
    }


def link_out(link: PostLink) -> dict[str, Any]:
    return {"url": link.url, "domain": link.domain, "title": link.title, "kind": link.kind}


def post_out(
    p: Post, channel: Channel, media: list[Media], links: list[PostLink], *, full: bool = False
) -> dict[str, Any]:
    text = p.text or ""
    out = {
        "id": p.tg_message_id,
        "date": p.date,
        "edit_date": p.edit_date,
        "html": p.html if full or len(text) <= 1200 else None,
        "text": text if full else text[:1200],
        "truncated": (not full) and len(text) > 1200,
        "views": p.views,
        "forwards": p.forwards,
        "reactions_total": p.reactions_total,
        "reactions": p.reactions,
        "media_kind": p.media_kind,
        "media": [media_out(m) for m in media],
        "links": [link_out(link) for link in links],
        "poll": p.poll,
        "forward_from": p.forward_from,
        "reply_to": p.reply_to_tg_message_id,
        "title": p.title,
        "summary": p.summary,
        "language": p.language,
        "is_deleted": p.is_deleted,
        "url": t_me_url(channel, p.tg_message_id),
    }
    return out


async def attach_media_links(
    db: AsyncSession, posts: list[Post]
) -> tuple[dict[int, list[Media]], dict[int, list[PostLink]]]:
    """Media for album roots spans all album members; keyed by root post id."""
    if not posts:
        return {}, {}
    ids = [p.id for p in posts]
    grouped = {p.grouped_id for p in posts if p.grouped_id}
    member_rows: list[tuple[int, int, int | None]] = []
    if grouped:
        member_rows = (
            await db.execute(
                select(Post.id, Post.tg_message_id, Post.grouped_id).where(
                    Post.channel_id == posts[0].channel_id, Post.grouped_id.in_(grouped)
                )
            )
        ).all()
    root_by_group = {p.grouped_id: p.id for p in posts if p.grouped_id}
    member_to_root = {
        row.id: root_by_group[row.grouped_id] for row in member_rows if row.grouped_id in root_by_group
    }
    all_ids = set(ids) | set(member_to_root)
    media = (
        await db.scalars(select(Media).where(Media.post_id.in_(all_ids)).order_by(Media.position, Media.id))
    ).all()
    links = (await db.scalars(select(PostLink).where(PostLink.post_id.in_(ids)).order_by(PostLink.id))).all()
    media_by: dict[int, list[Media]] = {}
    for m in media:
        root = member_to_root.get(m.post_id, m.post_id)
        media_by.setdefault(root, []).append(m)
    links_by: dict[int, list[PostLink]] = {}
    for link in links:
        links_by.setdefault(link.post_id, []).append(link)
    return media_by, links_by
