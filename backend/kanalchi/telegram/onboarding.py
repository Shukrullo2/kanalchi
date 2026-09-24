"""Channel resolution/join (runs in worker-telegram) and DNS verification (runs anywhere)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import dns.resolver
from sqlalchemy import select
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    UsernameNotOccupiedError,
)
from telethon.tl import functions
from telethon.tl import types as tl

from kanalchi.core import storage
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, TelegramAccount, Tenant
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings
from kanalchi.text.slug import slugify

log = get_logger(__name__)

_INVITE = re.compile(r"(?:t\.me/(?:joinchat/|\+)|tg://join\?invite=)([A-Za-z0-9_-]+)")


async def resolve_channel(
    tenant_id: int, link: str, account_id: int, allow_join_private: bool = False
) -> dict:
    from kanalchi.telegram.pool import get_pool

    pool = get_pool()
    client = pool.client(account_id)
    link = link.strip()
    invite = _INVITE.search(link)
    try:
        async with pool.lock(account_id):
            if invite:
                if not allow_join_private:
                    raise RuntimeError("private invite links require the 'join private channel' option")
                res = await client(functions.messages.ImportChatInviteRequest(invite.group(1)))
                entity = res.chats[0]
            else:
                entity = await client.get_entity(link)
            if not isinstance(entity, tl.Channel) or not entity.broadcast:
                raise RuntimeError("the link does not point to a Telegram channel")
            if getattr(entity, "left", False):
                await client(functions.channels.JoinChannelRequest(entity))
                entity = await client.get_entity(entity)
            full = await client(functions.channels.GetFullChannelRequest(entity))
            total = (await client.get_messages(entity, limit=0)).total
            photo_bytes = None
            try:
                photo_bytes = await client.download_profile_photo(entity, file=bytes)
            except Exception:  # noqa: BLE001
                pass
    except FloodWaitError as e:
        raise RuntimeError(f"Telegram asked to wait {e.seconds}s (FloodWait); retry later") from e
    except (UsernameNotOccupiedError, ChannelPrivateError, InviteHashExpiredError, ValueError) as e:
        raise RuntimeError(f"cannot resolve channel: {type(e).__name__}") from e

    photo_key = None
    if photo_bytes:
        from kanalchi.telegram.media import make_thumb

        thumb = make_thumb(photo_bytes, 320)
        if thumb:
            photo_key = f"{tenant_id}/channel/{entity.id}/photo.webp"
            await storage.upload_bytes(get_settings().s3_bucket_media, photo_key, thumb, "image/webp")

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise RuntimeError("tenant not found")
        existing = await db.scalar(select(Channel).where(Channel.tg_channel_id == entity.id))
        if existing and existing.tenant_id != tenant_id:
            raise RuntimeError(f"channel already belongs to tenant {existing.tenant_id}")
        ch = existing or await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        if ch is None:
            ch = Channel(tenant_id=tenant_id, tg_channel_id=entity.id)
            db.add(ch)
        ch.tg_channel_id = entity.id
        ch.telegram_account_id = account_id
        ch.access_hash = entity.access_hash
        ch.username = entity.username
        ch.title = entity.title or ""
        ch.about = full.full_chat.about
        ch.photo_key = photo_key or ch.photo_key
        ch.is_private = not bool(entity.username)
        ch.noforwards = bool(getattr(entity, "noforwards", False))
        ch.participants_count = full.full_chat.participants_count
        ch.backfill_total_estimate = total
        if not tenant.title:
            tenant.title = entity.title or ""
        # A channel onboarded without a domain of its own was given a placeholder under the
        # platform domain; now that its username is known, take that instead if it is free.
        if (tenant.settings or {}).get("auto_domain") and entity.username:
            wanted = slugify(entity.username)
            candidate = f"{wanted}.{get_settings().tenant_base_domain}"
            taken = await db.scalar(
                select(Tenant.id).where(
                    (Tenant.domain == candidate) | (Tenant.slug == wanted), Tenant.id != tenant_id
                )
            )
            if wanted and not taken and tenant.domain != candidate:
                old_domain = tenant.domain
                tenant.slug, tenant.domain = wanted, candidate
                await get_redis().delete(f"tenant:host:{old_domain}", f"tls:ask:{old_domain}")
        if ch.noforwards:
            tenant.settings = {**(tenant.settings or {}), "media_policy": "link_only"}
        await db.flush()
        out = {
            "channel_id": ch.id,
            "tg_channel_id": entity.id,
            "title": ch.title,
            "username": ch.username,
            "total": total,
            "noforwards": ch.noforwards,
        }
    log.info("onboarding.channel_resolved", tenant_id=tenant_id, **out)
    return out


PREVIEW_SAMPLE = 300


def _set_preview(tenant: Tenant, state: str) -> None:
    signup = {**((tenant.settings or {}).get("signup") or {}), "preview": state}
    tenant.settings = {**(tenant.settings or {}), "signup": signup}


async def mark_preview_failed(tenant_id: int) -> None:
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is not None:
            _set_preview(tenant, "failed")


async def preview_channel(tenant_id: int) -> dict:
    """Size up a channel that registered itself: subscribers and message count, read through any
    active account without joining, so the sign-up page can quote the import. Fills the channel
    row (but not its reader account: that is chosen when the admin starts the import)."""
    from kanalchi.core.billing import quote_for_posts
    from kanalchi.telegram.pool import get_pool

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise RuntimeError("tenant not found")
        username = ((tenant.settings or {}).get("signup") or {}).get("username")
        account_id = await db.scalar(
            select(TelegramAccount.id).where(TelegramAccount.status == "active").order_by(TelegramAccount.id)
        )
    if not username or account_id is None:
        log.info(
            "signup.preview.skipped", tenant_id=tenant_id, has_username=bool(username), account=account_id
        )
        await mark_preview_failed(tenant_id)
        return {"skipped": "no username" if not username else "no active account"}

    pool = get_pool()
    client = pool.client(account_id)
    try:
        async with pool.lock(account_id):
            entity = await client.get_entity(username)
            if not isinstance(entity, tl.Channel) or not entity.broadcast:
                raise RuntimeError("the link does not point to a Telegram channel")
            full = await client(functions.channels.GetFullChannelRequest(entity))
            total = (await client.get_messages(entity, limit=0)).total
            # A sample of recent posts gives the channel's own text length and how many posts
            # carry text at all, which is what the price actually depends on.
            sample = await client.get_messages(entity, limit=PREVIEW_SAMPLE)
    except FloodWaitError as e:
        raise RuntimeError(f"Telegram asked to wait {e.seconds}s (FloodWait); retry later") from e
    except (UsernameNotOccupiedError, ChannelPrivateError, ValueError) as e:
        raise RuntimeError(f"cannot resolve channel: {type(e).__name__}") from e

    from kanalchi.jobs.pipeline import CHARS_PER_TOKEN

    texts = [len(m.message or "") for m in sample if m is not None and not getattr(m, "action", None)]
    with_text = [n for n in texts if n > 0]
    avg_tokens = (sum(with_text) / len(with_text) / CHARS_PER_TOKEN) if with_text else None
    text_share = (len(with_text) / len(texts)) if texts else None

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        assert tenant is not None
        existing = await db.scalar(select(Channel).where(Channel.tg_channel_id == entity.id))
        if existing and existing.tenant_id != tenant_id:
            raise RuntimeError(f"channel already belongs to tenant {existing.tenant_id}")
        ch = existing or await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        if ch is None:
            ch = Channel(tenant_id=tenant_id, tg_channel_id=entity.id)
            db.add(ch)
        ch.tg_channel_id = entity.id
        ch.username = entity.username
        ch.title = entity.title or ""
        ch.about = full.full_chat.about
        ch.participants_count = full.full_chat.participants_count
        ch.backfill_total_estimate = total
        ch.noforwards = bool(getattr(entity, "noforwards", False))
        if not tenant.title:
            tenant.title = entity.title or ""
        tenant.onboarding_quote = quote_for_posts(
            total, source="telegram", avg_post_tokens=avg_tokens, text_share=text_share
        )
        _set_preview(tenant, "done")
        out = {
            "tg_channel_id": entity.id,
            "title": ch.title,
            "total": total,
            "quote": tenant.onboarding_quote,
        }
    log.info("signup.preview.done", tenant_id=tenant_id, total=total)
    return out


def verify_domain(domain: str) -> tuple[bool, str]:
    """DNS check: the domain (or its CNAME target) must resolve to PUBLIC_IP. Dev *.localhost always passes."""
    s = get_settings()
    domain = domain.lower().strip()
    if domain.endswith(".localhost") or domain == "localhost":
        return True, "local development domain"
    if not s.public_ip:
        return False, "PUBLIC_IP is not configured"
    try:
        answers = dns.resolver.resolve(domain, "A")
        ips = {r.address for r in answers}
    except Exception as exc:  # noqa: BLE001
        return False, f"DNS lookup failed: {type(exc).__name__}"
    if s.public_ip in ips:
        return True, f"resolves to {s.public_ip}"
    return False, f"resolves to {', '.join(sorted(ips))}, expected {s.public_ip}"


async def mark_domain_verified(tenant_id: int) -> None:
    async with session_scope() as db:
        t = await db.get(Tenant, tenant_id)
        if t:
            t.domain_verified_at = datetime.now(UTC)
