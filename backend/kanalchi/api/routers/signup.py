"""Self-serve sign-up on the platform domain: a blogger signs in with Telegram, adds their
channel, sees what the import costs, picks a plan and asks to be onboarded. The admin takes
it from there (payment by hand, then the import), and this API reports progress back."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.auth import SessionData
from kanalchi.api.deps import enforce_same_origin, get_db, require_user
from kanalchi.core import billing
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Post, Tenant, TenantMember
from kanalchi.core.settings import get_settings
from kanalchi.text.slug import slugify

log = get_logger(__name__)

router = APIRouter(prefix="/api/signup", tags=["signup"])
# The signed-in part; it is mounted under `router`, so no prefix of its own.
mine = APIRouter(dependencies=[Depends(require_user), Depends(enforce_same_origin)])

# @name, t.me/name, https://telegram.me/name/ — a public channel username, nothing else.
_USERNAME = re.compile(r"^(?:https?://)?(?:(?:www\.)?(?:t|telegram)\.me/|@)?([A-Za-z][A-Za-z0-9_]{3,31})/?$")


def parse_channel_username(link: str) -> str | None:
    """The username in a channel link, or None for anything that is not a public channel link."""
    link = link.strip()
    if "joinchat" in link or "/+" in link or link.startswith("+"):
        return None
    m = _USERNAME.match(link)
    return m.group(1).lower() if m else None


@router.get("/plans")
async def plans() -> dict:
    """Public: the plans and how the onboarding price is made, for the landing page."""
    s = get_settings()
    return {
        "currency": "USD",
        "plans": billing.plan_catalogue(),
        "onboarding": {
            "base_usd": s.onboarding_base_usd,
            "ai_markup": s.onboarding_ai_markup,
            "min_usd": s.onboarding_min_usd,
            "sample": billing.quote_for_posts(1000, source="sample"),
        },
    }


class ChannelIn(BaseModel):
    link: str = Field(min_length=4, max_length=200)


class ChannelPatch(BaseModel):
    plan: str | None = Field(default=None, pattern="^(archive|basic|premium)$")
    # The blogger's own guess at the archive size, used until Telegram has been asked.
    posts_estimate: int | None = Field(default=None, ge=1, le=2_000_000)


async def _mine(db: AsyncSession, user: SessionData, tenant_id: int) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.owner_user_id != user.user_id or tenant.status == "archived":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    return tenant


async def _out(db: AsyncSession, tenant: Tenant, user: SessionData) -> dict[str, Any]:
    s = get_settings()
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
    member = await db.scalar(
        select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.user_id)
    )
    imported = 0
    if channel is not None and tenant.status in {"backfilling", "indexing", "active"}:
        imported = (
            await db.scalar(select(func.count()).select_from(Post).where(Post.channel_id == channel.id)) or 0
        )
    signup = (tenant.settings or {}).get("signup") or {}
    return {
        "id": tenant.id,
        "slug": tenant.slug,
        "domain": tenant.domain,
        "url": s.public_url(tenant.domain),
        "title": tenant.title or (channel.title if channel else "") or signup.get("username", ""),
        "status": tenant.status,
        "plan": tenant.plan,
        "plan_monthly_usd": billing.plan_price_usd(tenant.plan),
        "subscription_status": tenant.subscription_status,
        "subscription_paid_until": tenant.subscription_paid_until,
        "onboarding_paid_at": tenant.onboarding_paid_at,
        "quote": tenant.onboarding_quote,
        "requested_at": signup.get("requested_at"),
        "verified": bool(member and member.verified_admin_at),
        "channel": {
            "username": (channel.username if channel else None) or signup.get("username"),
            "title": channel.title if channel else None,
            "participants_count": channel.participants_count if channel else None,
            "posts_estimate": channel.backfill_total_estimate if channel else None,
            "resolved": channel is not None,
        },
        "progress": {
            "imported": imported,
            "total": channel.backfill_total_estimate if channel else None,
            "backfill_status": channel.backfill_status if channel else None,
        },
        "created_at": tenant.created_at,
    }


@mine.get("/channels")
async def my_channels(
    user: SessionData = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Tenant)
            .where(Tenant.owner_user_id == user.user_id, Tenant.status != "archived")
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    return [await _out(db, t, user) for t in rows]


@mine.post("/channels", status_code=201)
async def add_channel(
    body: ChannelIn, user: SessionData = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    s = get_settings()
    username = parse_channel_username(body.link)
    if username is None:
        raise HTTPException(400, "send a public channel link or @username (private channels: contact us)")
    slug = slugify(username)
    domain = f"{slug}.{s.tenant_base_domain}"

    existing = await db.scalar(select(Tenant).where((Tenant.slug == slug) | (Tenant.domain == domain)))
    if existing is not None:
        if existing.owner_user_id == user.user_id and existing.status != "archived":
            return await _out(db, existing, user)
        raise HTTPException(409, "this channel is already on the platform")

    info = None
    if s.platform_bot_token:
        from kanalchi.telegram.verify import public_channel_info

        info = await public_channel_info(s.platform_bot_token, username)
        if info is None:
            raise HTTPException(400, "that username is not a public Telegram channel")
        taken = await db.scalar(
            select(Channel.tenant_id).where(Channel.tg_channel_id == info["tg_channel_id"])
        )
        if taken is not None:
            raise HTTPException(409, "this channel is already on the platform")

    tenant = Tenant(
        slug=slug,
        domain=domain,
        title=(info or {}).get("title") or "",
        status="onboarding",
        owner_user_id=user.user_id,
        source="self",
        domain_verified_at=datetime.now(UTC),
        settings={"auto_domain": True, "signup": {"username": username, "link": body.link.strip()}},
    )
    db.add(tenant)
    await db.flush()
    db.add(TenantMember(tenant_id=tenant.id, user_id=user.user_id, role="owner"))
    if info is not None:
        db.add(
            Channel(
                tenant_id=tenant.id,
                tg_channel_id=info["tg_channel_id"],
                username=username,
                title=info["title"],
                about=info["about"],
                participants_count=info["participants_count"],
            )
        )
    await db.flush()

    # Size and price the archive through a reader account; the page polls for the result.
    try:
        from kanalchi.jobs import telegram_jobs

        await telegram_jobs.channel_preview.defer_async(tenant_id=tenant.id)
    except Exception as exc:  # noqa: BLE001
        log.warning("signup.preview.defer_failed", tenant_id=tenant.id, error=str(exc)[:200])
    await _notify(f"New channel registered: @{username} by {user.name} (tg {user.tg_user_id}) → {domain}")
    log.info("signup.channel_added", tenant_id=tenant.id, username=username, user_id=user.user_id)
    return await _out(db, tenant, user)


@mine.get("/channels/{tenant_id}")
async def get_channel(
    tenant_id: int, user: SessionData = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _out(db, await _mine(db, user, tenant_id), user)


@mine.patch("/channels/{tenant_id}")
async def patch_channel(
    tenant_id: int,
    body: ChannelPatch,
    user: SessionData = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant = await _mine(db, user, tenant_id)
    if body.posts_estimate is not None:
        measured = (tenant.onboarding_quote or {}).get("source") == "telegram"
        if not measured:
            channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
            if channel is not None:
                channel.backfill_total_estimate = body.posts_estimate
            tenant.onboarding_quote = billing.quote_for_posts(body.posts_estimate, source="manual")
    if body.plan is not None:
        if tenant.subscription_status == "active":
            raise HTTPException(409, "the plan of a live channel is changed by the admin")
        tenant.plan = body.plan
    return await _out(db, tenant, user)


@mine.post("/channels/{tenant_id}/verify")
async def verify_owner(
    tenant_id: int, user: SessionData = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Ask Telegram whether the signed-in user administers the channel. Needs the platform bot to
    have been added to the channel, which is also what lets it post there later."""
    s = get_settings()
    tenant = await _mine(db, user, tenant_id)
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
    if not s.platform_bot_token or channel is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "verification is not available yet")
    from kanalchi.telegram.verify import is_channel_admin

    ok = await is_channel_admin(s.platform_bot_token, channel.tg_channel_id, user.tg_user_id)
    if ok:
        member = await db.scalar(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.user_id
            )
        )
        if member is None:
            member = TenantMember(tenant_id=tenant.id, user_id=user.user_id, role="owner")
            db.add(member)
        member.verified_admin_at = datetime.now(UTC)
        # Proven once; the studio on the channel's own domain will not ask Telegram again.
        member.invited = True
    return {"verified": ok}


@mine.post("/channels/{tenant_id}/request")
async def request_onboarding(
    tenant_id: int, user: SessionData = Depends(require_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Plan chosen, quote seen: ask the admin to take payment and start the import."""
    tenant = await _mine(db, user, tenant_id)
    if tenant.plan is None:
        raise HTTPException(400, "choose a plan first")
    if tenant.onboarding_quote is None:
        raise HTTPException(400, "the archive has not been sized yet")
    if tenant.subscription_status == "none":
        tenant.subscription_status = "pending"
    signup = {**((tenant.settings or {}).get("signup") or {}), "requested_at": datetime.now(UTC).isoformat()}
    tenant.settings = {**(tenant.settings or {}), "signup": signup}
    quote = tenant.onboarding_quote
    await _notify(
        f"Onboarding requested: @{signup.get('username')} ({tenant.domain})\n"
        f"plan {tenant.plan} (${billing.plan_price_usd(tenant.plan)}/mo), "
        f"import ${quote.get('price_usd')} for {quote.get('posts')} posts\n"
        f"by {user.name} (tg {user.tg_user_id}" + (f", @{user.username}" if user.username else "") + ")"
    )
    return await _out(db, tenant, user)


async def _notify(message: str) -> None:
    """Tell the admins on Telegram; a failure here must never fail the sign-up."""
    try:
        from kanalchi.jobs.periodic import _alert_admins

        await _alert_admins(message)
    except Exception as exc:  # noqa: BLE001
        log.warning("signup.notify_failed", error=str(exc)[:200])


router.include_router(mine)
