"""Publishing a draft through the tenant's own bot.

The post is written by the bot, but the archive is fed by the MTProto listener, so the same post
arrives twice. Both paths upsert on `(channel_id, tg_message_id)`, so whichever lands first wins and
the other fills in what it knows: the bot knows the draft it came from, the listener knows the views.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from sqlalchemy import select

from kanalchi.core import storage
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Draft, Tenant, Upload
from kanalchi.core.settings import get_settings
from kanalchi.telegram.formatting import DraftValidationError, validate
from kanalchi.telegram.verify import bot_can_post, bot_chat_id

log = get_logger(__name__)

MAX_ATTEMPTS = 3


class PublishError(RuntimeError):
    pass


async def _load_media(tenant_id: int, media: list[dict[str, Any]]) -> list[tuple[str, bytes, str]]:
    """(kind, bytes, filename) for each attachment, read back from MinIO."""
    s = get_settings()
    out: list[tuple[str, bytes, str]] = []
    async with session_scope() as db:
        for item in media:
            upload = await db.get(Upload, item.get("upload_id")) if item.get("upload_id") else None
            key = item.get("object_key") or (upload.object_key if upload else None)
            if not key:
                continue
            kind = item.get("kind") or (upload.kind if upload else "document")
            url = await storage.presigned_get(s.s3_bucket_uploads, key)
            out.append((kind, url, key.rsplit("/", 1)[-1]))
    return out


def _slot(value: datetime | str | None) -> int | None:
    """A schedule as whole UTC seconds, so a job can be matched to the schedule it was queued for."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


async def publish_draft(draft_id: int, scheduled_at: datetime | str | None = None) -> dict[str, Any]:
    """Send a draft to the channel. Idempotent: an already published draft is not sent twice.

    `scheduled_at` is the schedule this job was queued for. A queued job cannot be withdrawn, so
    cancelling or re-scheduling a post changes the row instead, and the stale job finds it no
    longer matches and steps aside.
    """
    import httpx

    from kanalchi.api.routers.webhooks import tenant_bot

    async with session_scope() as db:
        draft = await db.get(Draft, draft_id)
        if draft is None:
            raise PublishError("draft not found")
        if draft.status == "published":
            return {"skipped": "already published", "message_id": draft.published_tg_message_id}
        if draft.status not in {"scheduled", "publishing"}:
            return {"skipped": f"draft is {draft.status}, not waiting to be sent"}
        if scheduled_at is not None and _slot(scheduled_at) != _slot(draft.scheduled_at):
            return {"skipped": "superseded by a newer schedule"}
        tenant = await db.get(Tenant, draft.tenant_id)
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == draft.tenant_id))
        if tenant is None or channel is None or not tenant.bot_token_enc:
            raise PublishError("this channel has no bot configured")
        draft.status = "publishing"
        payload = {
            "html": draft.html,
            "media": list(draft.media or []),
            "disable_preview": bool(draft.disable_preview),
        }
        suggested = bool(draft.suggested_tags)
        db.expunge_all()

    from kanalchi.core.crypto import decrypt

    token = decrypt(tenant.bot_token_enc)
    can_post, detail = await bot_can_post(token, channel.tg_channel_id)
    if not can_post:
        await _fail(draft_id, f"the bot cannot post to the channel ({detail})")
        return {"failed": detail}

    try:
        html = validate(payload["html"], has_media=bool(payload["media"]), media_count=len(payload["media"]))
    except DraftValidationError as exc:
        await _fail(draft_id, str(exc))
        return {"failed": str(exc)}

    chat_id = bot_chat_id(channel.tg_channel_id)
    bot = tenant_bot(tenant)
    files = await _load_media(tenant.id, payload["media"])

    try:
        if not files:
            message = await bot.send_message(
                chat_id,
                html,
                parse_mode="HTML",
                disable_web_page_preview=payload["disable_preview"],
            )
        elif len(files) == 1:
            kind, url, filename = files[0]
            data = await _fetch(httpx, url)
            file = BufferedInputFile(data, filename=filename)
            if kind == "photo":
                message = await bot.send_photo(chat_id, file, caption=html or None, parse_mode="HTML")
            elif kind == "video":
                message = await bot.send_video(chat_id, file, caption=html or None, parse_mode="HTML")
            else:
                message = await bot.send_document(chat_id, file, caption=html or None, parse_mode="HTML")
        else:
            group: list[Any] = []
            for index, (kind, url, filename) in enumerate(files):
                data = await _fetch(httpx, url)
                file = BufferedInputFile(data, filename=filename)
                caption = html or None if index == 0 else None  # Telegram shows only the first caption
                cls = {"photo": InputMediaPhoto, "video": InputMediaVideo}.get(kind, InputMediaDocument)
                group.append(cls(media=file, caption=caption, parse_mode="HTML"))
            sent = await bot.send_media_group(chat_id, group)
            message = sent[0]
    except TelegramRetryAfter as exc:
        from kanalchi.jobs import publish_jobs

        await publish_jobs.publish.configure(schedule_in={"seconds": exc.retry_after + 2}).defer_async(
            draft_id=draft_id
        )
        async with session_scope() as db:
            row = await db.get(Draft, draft_id)
            if row:
                row.status = "scheduled"
        return {"retry_after": exc.retry_after}
    except TelegramForbiddenError as exc:
        await _fail(draft_id, f"the bot was blocked or removed from the channel: {exc}")
        return {"failed": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("publish.failed", draft_id=draft_id, error=str(exc)[:300])
        await _fail(draft_id, str(exc)[:500])
        return {"failed": str(exc)[:200]}

    async with session_scope() as db:
        row = await db.get(Draft, draft_id)
        row.status = "published"
        row.published_tg_message_id = message.message_id
        row.published_at = datetime.now(UTC)
        row.publish_error = None
        if row.idea_id:
            from kanalchi.core.models import Idea

            idea = await db.get(Idea, row.idea_id)
            if idea is not None:
                idea.status = "published"

    await _notify(tenant, channel, draft_id, message.message_id)
    if suggested:
        from kanalchi.jobs import publish_jobs

        await publish_jobs.file_tags.configure(schedule_in={"seconds": 45}).defer_async(draft_id=draft_id)
    log.info("publish.sent", draft_id=draft_id, message_id=message.message_id)
    return {"published": True, "message_id": message.message_id}


async def file_suggested_tags(draft_id: int) -> int | None:
    """Attach the draft's suggested tags to the post the listener stored for it.
    None means the post is not in the archive yet; a number is how many tags were filed."""
    from kanalchi.core.models import Post, PostTag, Tag

    async with session_scope() as db:
        draft = await db.get(Draft, draft_id)
        if draft is None or not draft.published_tg_message_id:
            return 0
        slugs = [t.get("slug") for t in (draft.suggested_tags or []) if isinstance(t, dict) and t.get("slug")]
        if not slugs:
            return 0
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == draft.tenant_id))
        if channel is None:
            return 0
        post_id = await db.scalar(
            select(Post.id).where(
                Post.channel_id == channel.id, Post.tg_message_id == draft.published_tg_message_id
            )
        )
        if post_id is None:
            return None
        tag_ids = (
            await db.scalars(
                select(Tag.id).where(
                    Tag.tenant_id == draft.tenant_id, Tag.slug.in_(slugs), Tag.status == "active"
                )
            )
        ).all()
        existing = set((await db.scalars(select(PostTag.tag_id).where(PostTag.post_id == post_id))).all())
        filed = 0
        for tag_id in tag_ids:
            if tag_id not in existing:
                db.add(
                    PostTag(
                        post_id=post_id,
                        tag_id=tag_id,
                        tenant_id=draft.tenant_id,
                        confidence=1.0,
                        source="manual",
                    )
                )
                filed += 1
    if filed:
        from kanalchi.jobs import index_jobs

        await index_jobs.recompute_counts.defer_async(tenant_id=draft.tenant_id)
    return filed


async def _fetch(httpx_module: Any, url: str) -> bytes:
    async with httpx_module.AsyncClient(timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def _fail(draft_id: int, reason: str) -> None:
    async with session_scope() as db:
        row = await db.get(Draft, draft_id)
        if row is None:
            return
        row.status = "failed"
        row.publish_error = reason[:500]
    log.warning("publish.failed", draft_id=draft_id, reason=reason[:200])


async def _notify(tenant: Tenant, channel: Channel, draft_id: int, message_id: int) -> None:
    """Tell the blogger in Telegram. Only possible if they have started the bot."""
    from kanalchi.api.routers.webhooks import tenant_bot
    from kanalchi.core.models import Draft as DraftModel
    from kanalchi.core.models import TenantMember

    async with session_scope() as db:
        draft = await db.get(DraftModel, draft_id)
        member = (
            await db.scalar(
                select(TenantMember).where(
                    TenantMember.tenant_id == tenant.id,
                    TenantMember.user_id == draft.user_id,
                    TenantMember.dm_chat_id.is_not(None),
                )
            )
            if draft and draft.user_id
            else None
        )
    if member is None:
        return
    link = (
        f"https://t.me/{channel.username}/{message_id}"
        if channel.username
        else f"https://t.me/c/{channel.tg_channel_id}/{message_id}"
    )
    try:
        await tenant_bot(tenant).send_message(member.dm_chat_id, f"Post yuborildi ✅\n{link}")
    except Exception as exc:  # noqa: BLE001
        log.info("publish.notify_failed", draft_id=draft_id, error=str(exc)[:200])


async def notify_failure(tenant_id: int, draft_id: int) -> None:
    from kanalchi.api.routers.webhooks import tenant_bot
    from kanalchi.core.models import Draft as DraftModel
    from kanalchi.core.models import TenantMember

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        draft = await db.get(DraftModel, draft_id)
        if tenant is None or draft is None or not tenant.bot_token_enc:
            return
        member = (
            await db.scalar(
                select(TenantMember).where(
                    TenantMember.tenant_id == tenant_id,
                    TenantMember.user_id == draft.user_id,
                    TenantMember.dm_chat_id.is_not(None),
                )
            )
            if draft.user_id
            else None
        )
        reason = draft.publish_error or "unknown error"
        db.expunge_all()
    if member is None:
        return
    try:
        await tenant_bot(tenant).send_message(
            member.dm_chat_id,
            f"Postni yuborib bo‘lmadi ⚠️\n{reason}\n\n{get_settings().public_url(tenant.domain, '/studio/drafts')}",
        )
    except Exception as exc:  # noqa: BLE001
        log.info("publish.notify_failed", draft_id=draft_id, error=str(exc)[:200])
