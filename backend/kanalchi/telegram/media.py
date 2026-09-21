"""Media download → MinIO with thumbnails, size cap and protected-channel policy."""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from telethon.errors import FloodWaitError
from telethon.tl import types as tl

from kanalchi.core import storage
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Media, Post, TelegramAccount, Tenant
from kanalchi.core.settings import get_settings
from kanalchi.telegram.ingest import t_me_url

log = get_logger(__name__)

THUMB_PX = 640
MAX_ATTEMPTS = 3


def make_thumb(src: bytes | Path, px: int = THUMB_PX) -> bytes | None:
    try:
        im = Image.open(io.BytesIO(src) if isinstance(src, bytes) else src)
        im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im
        im.thumbnail((px, px))
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=80, method=4)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.warning("media.thumb_failed", error=str(exc))
        return None


def _key(tenant_id: int, channel_id: int, msg_id: int, unique: str, ext: str) -> str:
    ext = (ext or "").lstrip(".") or "bin"
    return f"{tenant_id}/{channel_id}/{msg_id}/{unique}.{ext}"


async def fetch_media(media_id: int) -> dict:
    from kanalchi.jobs import telegram_jobs
    from kanalchi.telegram.pool import get_pool

    s = get_settings()
    async with session_scope() as db:
        media = await db.get(Media, media_id)
        if media is None or media.status in {"stored", "too_large", "protected"}:
            return {"skipped": True}
        post = await db.get(Post, media.post_id)
        channel = await db.get(Channel, post.channel_id)
        tenant = await db.get(Tenant, channel.tenant_id)
        account = await db.get(TelegramAccount, channel.telegram_account_id)
        db.expunge_all()

    external = t_me_url(channel, post.tg_message_id)
    policy = (tenant.settings or {}).get("media_policy", "store")
    if channel.noforwards or policy == "link_only":
        await _finish(media_id, status="protected", external_url=external)
        return {"protected": True}

    pool = get_pool()
    client = pool.client(account.id)
    peer = pool.input_peer(channel)
    tmpdir = Path(s.media_tmp_dir)
    await asyncio.to_thread(tmpdir.mkdir, parents=True, exist_ok=True)
    try:
        async with pool.lock(account.id):
            msg = await client.get_messages(peer, ids=post.tg_message_id)
            if not isinstance(msg, tl.Message) or msg.file is None:
                await _finish(media_id, status="failed", error="message or file no longer available")
                return {"failed": True}
            ext = (media.tg_file_ref or {}).get("ext") or msg.file.ext or ""
            key = _key(tenant.id, channel.id, post.tg_message_id, media.tg_file_unique_id, ext)
            thumb_key = f"{key.rsplit('.', 1)[0]}_thumb.webp"
            size = msg.file.size or 0

            thumb_bytes: bytes | None = None
            if media.kind in {"video", "animation", "document"} or size > s.media_max_bytes:
                try:
                    raw = await client.download_media(msg, file=bytes, thumb=-1)
                    if raw:
                        thumb_bytes = make_thumb(raw)
                except Exception as exc:  # noqa: BLE001
                    log.info("media.no_embedded_thumb", media_id=media_id, error=str(exc))

            if size > s.media_max_bytes:
                if thumb_bytes:
                    await storage.upload_bytes(s.s3_bucket_media, thumb_key, thumb_bytes, "image/webp")
                await _finish(
                    media_id,
                    status="too_large",
                    external_url=external,
                    thumb_key=thumb_key if thumb_bytes else None,
                )
                return {"too_large": True}

            with tempfile.NamedTemporaryFile(
                dir=tmpdir, suffix=f".{ext.lstrip('.') or 'bin'}", delete=False
            ) as tf:
                tmp_path = Path(tf.name)
            try:
                await client.download_media(msg, file=str(tmp_path))
                await storage.upload_file(s.s3_bucket_media, key, tmp_path, media.mime)
                if media.kind == "photo":
                    thumb_bytes = make_thumb(tmp_path)
                if thumb_bytes:
                    await storage.upload_bytes(s.s3_bucket_media, thumb_key, thumb_bytes, "image/webp")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    except FloodWaitError as e:
        await telegram_jobs.fetch_media.configure(schedule_in={"seconds": e.seconds + 5}).defer_async(
            media_id=media_id
        )
        return {"flood_wait": e.seconds}
    except Exception as exc:  # noqa: BLE001
        async with session_scope() as db:
            m = await db.get(Media, media_id)
            m.attempts = (m.attempts or 0) + 1
            m.error = str(exc)[:500]
            if m.attempts >= MAX_ATTEMPTS:
                m.status = "failed"
                m.external_url = external
            attempts = m.attempts
        if attempts < MAX_ATTEMPTS:
            await telegram_jobs.fetch_media.configure(schedule_in={"seconds": 60 * attempts}).defer_async(
                media_id=media_id
            )
        log.warning("media.fetch_failed", media_id=media_id, attempts=attempts, error=str(exc))
        return {"error": str(exc)}

    await _finish(
        media_id,
        status="stored",
        object_key=key,
        thumb_key=thumb_key if thumb_bytes else None,
        size_bytes=size,
    )
    log.info("media.stored", media_id=media_id, key=key, size=size)
    return {"stored": True, "key": key}


async def _finish(media_id: int, **values) -> None:  # noqa: ANN003
    async with session_scope() as db:
        m = await db.get(Media, media_id)
        if m is None:
            return
        for k, v in values.items():
            setattr(m, k, v)
        m.updated_at = datetime.now(UTC)


async def pending_media_ids(tenant_id: int, limit: int = 500) -> list[int]:
    async with session_scope() as db:
        return list(
            (
                await db.scalars(
                    select(Media.id)
                    .where(Media.tenant_id == tenant_id, Media.status == "pending")
                    .limit(limit)
                )
            ).all()
        )
