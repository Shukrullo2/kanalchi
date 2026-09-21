"""Telethon Message → posts/media/links rows; backfill chunks; live updates; resync."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from itertools import groupby
from typing import Any

import tldextract
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError
from telethon.tl import types as tl

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Media, Post, PostLink, TelegramAccount, Tenant
from kanalchi.text.normalize import normalize
from kanalchi.text.tg_html import entities_to_html, extract_urls

log = get_logger(__name__)

CHUNK = 1000


# ----------------------------------------------------------------------------- conversion
def _reactions(msg: tl.Message) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not msg.reactions or not msg.reactions.results:
        return out
    for r in msg.reactions.results:
        rx = r.reaction
        if isinstance(rx, tl.ReactionEmoji):
            out.append({"emoji": rx.emoticon, "count": r.count})
        elif isinstance(rx, tl.ReactionCustomEmoji):
            out.append({"custom_emoji_id": rx.document_id, "count": r.count})
        elif isinstance(rx, tl.ReactionPaid):
            out.append({"paid": True, "count": r.count})
    return out


def _forward(msg: tl.Message) -> dict[str, Any] | None:
    f = msg.fwd_from
    if f is None:
        return None
    out: dict[str, Any] = {
        "date": f.date.isoformat() if f.date else None,
        "channel_post": f.channel_post,
        "post_author": f.post_author,
        "from_name": f.from_name,
    }
    if isinstance(f.from_id, tl.PeerChannel):
        out["channel_id"] = f.from_id.channel_id
    elif isinstance(f.from_id, tl.PeerUser):
        out["user_id"] = f.from_id.user_id
    try:
        chat = (
            msg.forward.chat if msg.forward else None
        )  # populated from the same API response, no extra request
        if chat is not None:
            out["title"] = getattr(chat, "title", None) or getattr(chat, "first_name", None)
            out["username"] = getattr(chat, "username", None)
    except Exception:  # noqa: BLE001
        pass
    return out


def _poll(msg: tl.Message) -> dict[str, Any] | None:
    media = msg.media
    if not isinstance(media, tl.MessageMediaPoll):
        return None
    poll, results = media.poll, media.results
    voters = {a.option: a.voters for a in (results.results or [])} if results else {}
    return {
        "question": getattr(poll.question, "text", poll.question),
        "answers": [
            {"text": getattr(a.text, "text", a.text), "voters": voters.get(a.option)} for a in poll.answers
        ],
        "total_voters": results.total_voters if results else None,
        "closed": poll.closed,
        "quiz": poll.quiz,
    }


def _media_item(msg: tl.Message) -> dict[str, Any] | None:
    """One media item per message (albums = one message per item)."""
    media = msg.media
    if media is None or isinstance(media, tl.MessageMediaWebPage | tl.MessageMediaPoll):
        return None
    f = msg.file
    if f is None:
        return None
    kind = "document"
    if isinstance(media, tl.MessageMediaPhoto):
        kind = "photo"
    elif msg.sticker:
        kind = "sticker"
    elif msg.gif:
        kind = "animation"
    elif msg.video or msg.video_note:
        kind = "video"
    elif msg.voice:
        kind = "voice"
    elif msg.audio:
        kind = "audio"
    ident = getattr(msg.photo, "id", None) or getattr(msg.document, "id", None) or msg.id
    return {
        "tg_file_unique_id": str(ident),
        "kind": kind,
        "mime": f.mime_type,
        "size_bytes": f.size,
        "width": f.width,
        "height": f.height,
        "duration_s": int(f.duration) if f.duration else None,
        "file_name": f.name,
        "ext": f.ext or "",
    }


def message_fields(msg: tl.Message) -> dict[str, Any] | None:
    """Columns for `posts` from a Telethon message. Returns None for service messages."""
    if not isinstance(msg, tl.Message):
        return None
    entities = [e.to_dict() for e in (msg.entities or [])]
    text = msg.message or ""
    item = _media_item(msg)
    poll = _poll(msg)
    media_kind = item["kind"] if item else ("poll" if poll else "none")
    file_ids = [item["tg_file_unique_id"]] if item else []
    reactions = _reactions(msg)
    return {
        "tg_message_id": msg.id,
        "grouped_id": msg.grouped_id,
        "text": text,
        "text_norm": normalize(text),
        "entities": entities,
        "html": entities_to_html(text, entities),
        "date": msg.date.astimezone(UTC) if msg.date else datetime.now(UTC),
        "edit_date": msg.edit_date.astimezone(UTC) if msg.edit_date else None,
        "views": msg.views or 0,
        "forwards": msg.forwards or 0,
        "reactions": reactions,
        "reactions_total": sum(r["count"] for r in reactions),
        "reply_to_tg_message_id": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        "forward_from": _forward(msg),
        "media_kind": media_kind,
        "poll": poll,
        "content_hash": hashlib.sha256((text + "|" + ",".join(sorted(file_ids))).encode()).hexdigest(),
        "_media": item,
        "_urls": extract_urls(text, entities),
    }


def engagement(views: int, forwards: int, reactions_total: int) -> float:
    return reactions_total * 5 + forwards * 10 + views / 100


# ----------------------------------------------------------------------------- upsert
async def upsert_messages(
    db: AsyncSession, channel: Channel, messages: list[tl.Message]
) -> tuple[list[int], list[int]]:
    """Insert/update posts for a batch. Returns (changed_post_ids, new_media_ids)."""
    tenant_id = channel.tenant_id
    changed: list[int] = []
    media_ids: list[int] = []
    for msg in messages:
        fields = message_fields(msg)
        if fields is None:
            continue
        item = fields.pop("_media")
        urls = fields.pop("_urls")
        fields["engagement_score"] = engagement(
            fields["views"], fields["forwards"], fields["reactions_total"]
        )
        stmt = insert(Post).values(
            tenant_id=tenant_id, channel_id=channel.id, is_album_root=fields["grouped_id"] is None, **fields
        )
        counters = {
            k: fields[k]
            for k in ("views", "forwards", "reactions", "reactions_total", "engagement_score", "edit_date")
        }
        content = {
            k: fields[k]
            for k in (
                "text",
                "text_norm",
                "entities",
                "html",
                "media_kind",
                "poll",
                "content_hash",
                "forward_from",
                "reply_to_tg_message_id",
            )
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_posts_channel_msg",
            set_={**counters, **content, "is_deleted": False, "deleted_at": None},
        ).returning(Post.id)
        # Fetch the previous hash first so we can tell counter-only updates from content changes.
        prev = await db.execute(
            select(Post.id, Post.content_hash).where(
                Post.channel_id == channel.id, Post.tg_message_id == msg.id
            )
        )
        prev_row = prev.first()
        row = (await db.execute(stmt)).first()
        post_id = row.id
        is_new = prev_row is None
        content_changed = is_new or prev_row.content_hash != fields["content_hash"]
        if content_changed:
            changed.append(post_id)
            if not is_new:
                await db.execute(update(Post).where(Post.id == post_id).values(index_status="pending"))
            # links: replace
            await db.execute(PostLink.__table__.delete().where(PostLink.post_id == post_id))
            for u in urls[:50]:
                ext = tldextract.extract(u)
                domain = ".".join(p for p in (ext.domain, ext.suffix) if p) or ""
                db.add(
                    PostLink(
                        tenant_id=tenant_id,
                        post_id=post_id,
                        url=u[:2000],
                        url_norm=u.lower().rstrip("/")[:2000],
                        domain=domain.lower()[:253],
                    )
                )
        if item:
            mstmt = (
                insert(Media)
                .values(
                    tenant_id=tenant_id,
                    post_id=post_id,
                    position=0,
                    tg_file_unique_id=item["tg_file_unique_id"],
                    kind=item["kind"],
                    mime=item["mime"],
                    size_bytes=item["size_bytes"],
                    width=item["width"],
                    height=item["height"],
                    duration_s=item["duration_s"],
                    file_name=item["file_name"],
                    tg_file_ref={"msg_id": msg.id, "ext": item["ext"]},
                )
                .on_conflict_do_nothing(constraint="uq_media_post_file")
                .returning(Media.id)
            )
            mid = (await db.execute(mstmt)).scalar()
            if mid:
                media_ids.append(mid)
    await fix_album_roots(
        db, channel.id, {m.grouped_id for m in messages if isinstance(m, tl.Message) and m.grouped_id}
    )
    return changed, media_ids


async def fix_album_roots(db: AsyncSession, channel_id: int, grouped_ids: set[int]) -> None:
    """Album root = the member carrying the caption, else the lowest message id. Root gets media_kind='album'."""
    for gid in grouped_ids:
        rows = (
            await db.execute(
                select(Post.id, Post.tg_message_id, Post.text)
                .where(Post.channel_id == channel_id, Post.grouped_id == gid)
                .order_by(Post.tg_message_id)
            )
        ).all()
        if not rows:
            continue
        root = next((r for r in rows if (r.text or "").strip()), rows[0])
        ids = [r.id for r in rows]
        await db.execute(update(Post).where(Post.id.in_(ids)).values(is_album_root=False))
        await db.execute(
            update(Post)
            .where(Post.id == root.id)
            .values(is_album_root=True, media_kind="album" if len(rows) > 1 else Post.media_kind)
        )
        # position media by message order
        for pos, r in enumerate(rows):
            await db.execute(update(Media).where(Media.post_id == r.id).values(position=pos))


# ----------------------------------------------------------------------------- flows
async def _load(channel_id: int) -> tuple[Channel, Tenant, TelegramAccount]:
    async with session_scope() as db:
        channel = await db.get(Channel, channel_id)
        if channel is None:
            raise RuntimeError(f"channel {channel_id} not found")
        tenant = await db.get(Tenant, channel.tenant_id)
        account = (
            await db.get(TelegramAccount, channel.telegram_account_id)
            if channel.telegram_account_id
            else None
        )
        if tenant is None or account is None:
            raise RuntimeError(f"channel {channel_id} has no tenant/account")
        db.expunge_all()
        return channel, tenant, account


async def _after_upsert(channel: Channel, changed: list[int], media_ids: list[int]) -> None:
    from kanalchi.jobs import index_jobs, telegram_jobs

    for mid in media_ids:
        await telegram_jobs.fetch_media.defer_async(media_id=mid)
    for pid in changed:
        await index_jobs.index_post.defer_async(post_id=pid)


async def backfill_chunk(channel_id: int) -> dict[str, Any]:
    """One resumable step of history import (also used as gap-fill after restarts)."""
    from kanalchi.jobs import telegram_jobs
    from kanalchi.telegram.pool import get_pool

    channel, tenant, account = await _load(channel_id)
    pool = get_pool()
    client = pool.client(account.id)
    peer = pool.input_peer(channel)
    messages: list[tl.Message] = []
    try:
        async with pool.lock(account.id):
            if channel.backfill_total_estimate is None:
                total = (await client.get_messages(peer, limit=0)).total
                async with session_scope() as db:
                    await db.execute(
                        update(Channel)
                        .where(Channel.id == channel_id)
                        .values(backfill_total_estimate=total, backfill_status="running")
                    )
            async for m in client.iter_messages(
                peer, reverse=True, min_id=channel.backfill_checkpoint, limit=CHUNK
            ):
                messages.append(m)
    except FloodWaitError as e:
        await _flood_wait(account.id, e.seconds)
        await telegram_jobs.backfill_chunk.configure(
            schedule_in={"seconds": e.seconds + 5}, queueing_lock=f"backfill:{channel_id}"
        ).defer_async(channel_id=channel_id)
        return {"flood_wait": e.seconds}

    if messages:
        async with session_scope() as db:
            ch = await db.get(Channel, channel_id)
            changed, media_ids = await upsert_messages(db, ch, messages)
            ch.backfill_checkpoint = max(m.id for m in messages)
            ch.last_live_update_at = datetime.now(UTC)
        await _after_upsert(channel, changed, media_ids)
        log.info(
            "backfill.chunk", channel_id=channel_id, n=len(messages), checkpoint=max(m.id for m in messages)
        )

    if len(messages) >= CHUNK:
        await telegram_jobs.backfill_chunk.configure(
            schedule_in={"seconds": 2}, queueing_lock=f"backfill:{channel_id}"
        ).defer_async(channel_id=channel_id)
        return {"n": len(messages), "more": True}

    async with session_scope() as db:
        ch = await db.get(Channel, channel_id)
        first_done = ch.backfill_status != "done"
        ch.backfill_status = "done"
        t = await db.get(Tenant, ch.tenant_id)
        if t.status == "backfilling":
            t.status = "active"
    if first_done:
        from kanalchi.jobs import index_jobs

        await index_jobs.index_backlog.defer_async(tenant_id=channel.tenant_id)
        log.info("backfill.done", channel_id=channel_id)
    return {"n": len(messages), "more": False}


async def _flood_wait(account_id: int, seconds: int) -> None:
    async with session_scope() as db:
        acc = await db.get(TelegramAccount, account_id)
        if acc:
            acc.flood_wait_until = datetime.now(UTC) + timedelta(seconds=seconds)
            acc.health = {
                **(acc.health or {}),
                "last_flood_wait_s": seconds,
                "last_error_at": datetime.now(UTC).isoformat(),
            }
    log.warning("telethon.flood_wait", account_id=account_id, seconds=seconds)


async def ingest_live_message(channel_id: int, msg: tl.Message, edited: bool = False) -> None:
    async with session_scope() as db:
        channel = await db.get(Channel, channel_id)
        if channel is None:
            return
        changed, media_ids = await upsert_messages(db, channel, [msg])
        channel.last_live_update_at = datetime.now(UTC)
        if not edited and msg.id > channel.backfill_checkpoint and channel.backfill_status == "done":
            channel.backfill_checkpoint = msg.id
    await _after_upsert(channel, changed, media_ids)
    log.info("live.message", channel_id=channel_id, msg_id=msg.id, edited=edited, changed=bool(changed))


async def mark_deleted(channel_id: int, tg_message_ids: list[int]) -> None:
    async with session_scope() as db:
        await db.execute(
            update(Post)
            .where(
                Post.channel_id == channel_id,
                Post.tg_message_id.in_(tg_message_ids),
                Post.is_deleted.is_(False),
            )
            .values(is_deleted=True, deleted_at=datetime.now(UTC))
        )
    log.info("live.deleted", channel_id=channel_id, ids=tg_message_ids[:10], n=len(tg_message_ids))


async def resync(channel_id: int, days: int) -> dict[str, Any]:
    """Refresh views/forwards/reactions/edits for recent posts; detect deletions."""
    from kanalchi.telegram.pool import get_pool

    channel, tenant, account = await _load(channel_id)
    since = datetime.now(UTC) - timedelta(days=days)
    async with session_scope() as db:
        ids = (
            await db.scalars(
                select(Post.tg_message_id)
                .where(Post.channel_id == channel_id, Post.date >= since, Post.is_deleted.is_(False))
                .order_by(Post.tg_message_id)
            )
        ).all()
    if not ids:
        return {"n": 0}
    pool = get_pool()
    client = pool.client(account.id)
    peer = pool.input_peer(channel)
    updated = deleted = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        try:
            async with pool.lock(account.id):
                msgs = await client.get_messages(peer, ids=chunk)
        except FloodWaitError as e:
            await _flood_wait(account.id, e.seconds)
            break
        present = [m for m in msgs if isinstance(m, tl.Message)]
        gone = [mid for mid, m in zip(chunk, msgs, strict=False) if m is None]
        async with session_scope() as db:
            ch = await db.get(Channel, channel_id)
            changed, media_ids = await upsert_messages(db, ch, present)
            if gone:
                await db.execute(
                    update(Post)
                    .where(Post.channel_id == channel_id, Post.tg_message_id.in_(gone))
                    .values(is_deleted=True, deleted_at=datetime.now(UTC))
                )
            ch.last_resync_at = datetime.now(UTC)
        await _after_upsert(channel, changed, media_ids)
        updated += len(present)
        deleted += len(gone)
    log.info("resync.done", channel_id=channel_id, days=days, updated=updated, deleted=deleted)
    return {"n": updated, "deleted": deleted}


def t_me_url(channel: Channel, tg_message_id: int) -> str:
    if channel.username:
        return f"https://t.me/{channel.username}/{tg_message_id}"
    return f"https://t.me/c/{channel.tg_channel_id}/{tg_message_id}"


def group_by_album(messages: list[tl.Message]) -> list[list[tl.Message]]:
    """Utility for tests/tools: contiguous grouping by grouped_id."""
    return [list(g) for _, g in groupby(messages, key=lambda m: m.grouped_id or m.id)]
