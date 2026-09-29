"""Channel resolution/join (runs in worker-telegram) and DNS verification (runs anywhere)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

import dns.resolver
from sqlalchemy import select
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl import functions
from telethon.tl import types as tl

from kanalchi.core import storage
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, ChannelQuote, TelegramAccount, Tenant
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


async def _measure_with(client, username: str) -> dict:  # noqa: ANN001
    entity = await client.get_entity(username)
    if not isinstance(entity, tl.Channel) or not entity.broadcast:
        raise ValueError("not a Telegram channel")
    full = await client(functions.channels.GetFullChannelRequest(entity))
    total = (await client.get_messages(entity, limit=0)).total
    # A sample of recent posts gives the channel's own text length and how many posts carry
    # text at all, which is what the price actually depends on.
    sample = await client.get_messages(entity, limit=PREVIEW_SAMPLE)
    texts = [len(m.message or "") for m in sample if m is not None and not getattr(m, "action", None)]
    with_text = [n for n in texts if n > 0]
    return {
        "title": entity.title or "",
        "participants_count": full.full_chat.participants_count,
        "total": total,
        "avg_chars": (sum(with_text) / len(with_text)) if with_text else None,
        "text_share": (len(with_text) / len(texts)) if texts else None,
    }


async def measure_channel(username: str) -> dict:
    """Size up a public channel for a sign-up quote through a reader account, without joining.

    Every connected account is tried in turn, so one in a FloodWait (or busy with a long
    backfill) does not fail the quote. Whatever happens, the quote row ends up done or failed:
    a web-preview estimate already on it stays as the answer when Telegram cannot be asked."""
    from kanalchi.core.billing import quote_for_posts, quote_report
    from kanalchi.jobs.pipeline import CHARS_PER_TOKEN
    from kanalchi.telegram.pool import get_pool

    pool = get_pool()
    async with session_scope() as db:
        active = (
            await db.scalars(
                select(TelegramAccount.id)
                .where(TelegramAccount.status == "active")
                .order_by(TelegramAccount.id)
            )
        ).all()
    account_ids = [a for a in active if a in pool.accounts]

    measured: dict | None = None
    errors: list[str] = []
    for account_id in account_ids:
        try:
            # A short wait for the lock: a backfill chunk may be holding it for minutes.
            lock = pool.lock(account_id)
            await asyncio.wait_for(lock.acquire(), timeout=90)
            try:
                measured = await _measure_with(pool.client(account_id), username)
            finally:
                lock.release()
            break
        except (UsernameNotOccupiedError, UsernameInvalidError, ChannelPrivateError, ValueError) as e:
            errors.append(f"not a public channel ({type(e).__name__})")
            break  # another account will not see it either
        except FloodWaitError as e:
            errors.append(f"account {account_id}: FloodWait {e.seconds}s")
        except Exception as e:  # noqa: BLE001
            errors.append(f"account {account_id}: {type(e).__name__}: {str(e)[:120]}")
    if not account_ids:
        errors.append("no connected reader account")

    async with session_scope() as db:
        row = await db.scalar(select(ChannelQuote).where(ChannelQuote.username == username))
        if row is None:
            return {"skipped": "quote row gone"}
        before = (row.quote or {}).get("price_uzs")
        if measured is not None:
            row.title = measured["title"] or row.title
            row.participants_count = measured["participants_count"] or row.participants_count
            avg = measured["avg_chars"]
            row.quote = quote_for_posts(
                measured["total"],
                source="telegram",
                avg_post_tokens=avg / CHARS_PER_TOKEN if avg else None,
                text_share=measured["text_share"],
            )
            row.status, row.error = "done", None
        else:
            row.status = "done" if row.quote else "failed"
            row.error = "; ".join(errors)[:500]
        out = {"username": username, "status": row.status, "error": row.error}
        # Follow up on the report the API sent: only when Telegram changed the price, or nothing
        # could be measured at all.
        report = None
        if measured is not None and row.quote["price_uzs"] != before:
            report = quote_report(
                username, row.title, row.participants_count, row.quote, "Measured by Telegram"
            )
        elif row.status == "failed":
            report = quote_report(username, row.title, row.participants_count, None, "Could not price")
            report += f"\n⚠️ {row.error}"
    if report:
        from kanalchi.jobs.periodic import _alert_admins

        try:
            await _alert_admins(report)
        except Exception as exc:  # noqa: BLE001
            log.warning("signup.quote.report_failed", error=str(exc)[:200])
    log.info("signup.quote.measured", **out, measured=measured is not None)
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
