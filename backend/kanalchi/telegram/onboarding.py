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
from kanalchi.core.models import Channel, Tenant
from kanalchi.core.settings import get_settings

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
