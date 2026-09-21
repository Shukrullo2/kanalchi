"""Admin onboarding: Telegram accounts (login handshake) and the channel wizard."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import enforce_same_origin, get_db, require_admin
from kanalchi.core.crypto import encrypt
from kanalchi.core.jobs import create_job_run
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, TelegramAccount, Tenant
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings
from kanalchi.jobs import telegram_jobs
from kanalchi.telegram.onboarding import mark_domain_verified, verify_domain
from kanalchi.telegram.verify import bot_can_post

log = get_logger(__name__)
router = APIRouter(
    prefix="/api/admin", tags=["onboarding"], dependencies=[Depends(require_admin), Depends(enforce_same_origin)]
)

LOGIN_SECRET_TTL = 600


def _account_out(a: TelegramAccount) -> dict[str, Any]:
    return {
        "id": a.id,
        "phone": a.phone,
        "display_name": a.display_name,
        "tg_user_id": a.tg_user_id,
        "status": a.status,
        "health": a.health or {},
        "flood_wait_until": a.flood_wait_until,
        "last_seen_at": a.last_seen_at,
    }


# --------------------------------------------------------------------- accounts
class AccountCreate(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


@router.post("/accounts", status_code=201)
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_db)) -> dict:
    s = get_settings()
    if not s.tg_api_id or not s.tg_api_hash:
        raise HTTPException(503, "TG_API_ID / TG_API_HASH are not configured on the server")
    phone = body.phone.strip().replace(" ", "")
    acc = await db.scalar(select(TelegramAccount).where(TelegramAccount.phone == phone))
    if acc is None:
        acc = TelegramAccount(phone=phone, status="pending_code")
        db.add(acc)
        await db.flush()
    elif acc.status == "active":
        raise HTTPException(409, "account is already signed in")
    acc.status = "pending_code"
    acc.health = {**(acc.health or {}), "login_stage": "requested", "last_error": None}
    await db.flush()
    await telegram_jobs.account_login_start.defer_async(account_id=acc.id)
    return _account_out(acc)


class AccountSecret(BaseModel):
    value: str = Field(min_length=1, max_length=256)


async def _stash(account_id: int, kind: str, value: str) -> None:
    """Login codes/passwords travel through Redis encrypted; only worker-telegram reads them."""
    await get_redis().set(f"tglogin:{account_id}:{kind}", encrypt(value), ex=LOGIN_SECRET_TTL)


@router.post("/accounts/{account_id}/code")
async def submit_code(account_id: int, body: AccountSecret, db: AsyncSession = Depends(get_db)) -> dict:
    acc = await db.get(TelegramAccount, account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    await _stash(account_id, "code", body.value.strip())
    await telegram_jobs.account_login_code.defer_async(account_id=account_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/password")
async def submit_password(account_id: int, body: AccountSecret, db: AsyncSession = Depends(get_db)) -> dict:
    acc = await db.get(TelegramAccount, account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    await _stash(account_id, "password", body.value)
    await telegram_jobs.account_login_password.defer_async(account_id=account_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/resend")
async def resend_code(account_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    acc = await db.get(TelegramAccount, account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    acc.status = "pending_code"
    await telegram_jobs.account_login_start.defer_async(account_id=account_id)
    return {"ok": True}


@router.delete("/accounts/{account_id}")
async def disable_account(account_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    acc = await db.get(TelegramAccount, account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    in_use = await db.scalar(select(Channel.id).where(Channel.telegram_account_id == account_id))
    if in_use:
        raise HTTPException(409, "account still serves a channel; reassign it first")
    acc.status = "disabled"
    acc.session_enc = None
    return {"ok": True}


@router.get("/accounts/{account_id}")
async def get_account(account_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    acc = await db.get(TelegramAccount, account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    return _account_out(acc)


# --------------------------------------------------------------------- channel wizard
class ChannelLink(BaseModel):
    link: str = Field(min_length=3, max_length=300)
    account_id: int
    allow_join_private: bool = False


@router.post("/tenants/{tenant_id}/channel")
async def attach_channel(tenant_id: int, body: ChannelLink, db: AsyncSession = Depends(get_db)) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    acc = await db.get(TelegramAccount, body.account_id)
    if acc is None or acc.status != "active":
        raise HTTPException(400, "pick a signed-in Telegram account")
    job_run_id = await create_job_run(tenant_id, "resolve", {"link": body.link, "account_id": body.account_id})
    await telegram_jobs.channel_resolve.defer_async(
        tenant_id=tenant_id,
        link=body.link.strip(),
        account_id=body.account_id,
        allow_join_private=body.allow_join_private,
        job_run_id=job_run_id,
    )
    return {"job_run_id": job_run_id}


class BotToken(BaseModel):
    token: str = Field(min_length=20, max_length=128)


@router.post("/tenants/{tenant_id}/bot")
async def set_bot(tenant_id: int, body: BotToken, db: AsyncSession = Depends(get_db)) -> dict:
    from aiogram import Bot

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    if channel is None:
        raise HTTPException(400, "attach the channel first")
    token = body.token.strip()
    try:
        async with Bot(token) as bot:
            me = await bot.get_me()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bot token rejected by Telegram: {type(exc).__name__}") from exc

    ok, detail = await bot_can_post(token, channel.tg_channel_id)
    if not ok:
        raise HTTPException(400, f"add @{me.username} to the channel as an admin with 'Post messages' ({detail})")

    tenant.bot_token_enc = encrypt(token)
    tenant.bot_id = me.id
    tenant.bot_username = me.username
    tenant.webhook_secret = tenant.webhook_secret or secrets.token_urlsafe(24)
    await db.flush()

    webhook_url = get_settings().public_url(tenant.domain, f"/tg/webhook/{tenant.id}/{tenant.webhook_secret}")
    webhook_set = False
    webhook_error = None
    try:
        async with Bot(token) as bot:
            await bot.set_webhook(
                webhook_url,
                secret_token=tenant.webhook_secret,
                drop_pending_updates=True,
                allowed_updates=["message", "channel_post", "callback_query"],
            )
        webhook_set = True
    except Exception as exc:  # noqa: BLE001
        webhook_error = str(exc)  # e.g. the domain has no public certificate yet
    return {
        "bot_username": me.username,
        "bot_id": me.id,
        "can_post": True,
        "webhook_url": webhook_url,
        "webhook_set": webhook_set,
        "webhook_error": webhook_error,
        "setdomain_hint": f"/setdomain → @{me.username} → {tenant.domain}",
    }


@router.post("/tenants/{tenant_id}/verify-domain")
async def verify_tenant_domain(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    ok, detail = verify_domain(tenant.domain)
    if ok:
        await mark_domain_verified(tenant_id)
        await get_redis().delete(f"tls:ask:{tenant.domain}")
    return {"ok": ok, "detail": detail, "domain": tenant.domain}


@router.post("/tenants/{tenant_id}/start")
async def start_backfill(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    if channel is None:
        raise HTTPException(400, "attach the channel first")
    if channel.telegram_account_id is None:
        raise HTTPException(400, "channel has no Telegram account")
    tenant.status = "backfilling"
    channel.backfill_status = "running"
    job_run_id = await create_job_run(tenant_id, "backfill", {"channel_id": channel.id})
    try:
        await telegram_jobs.backfill_chunk.configure(queueing_lock=f"backfill:{channel.id}").defer_async(
            channel_id=channel.id
        )
    except Exception as exc:  # noqa: BLE001
        if "already" not in str(exc).lower():
            raise
    return {"job_run_id": job_run_id, "channel_id": channel.id}


@router.post("/tenants/{tenant_id}/resync")
async def trigger_resync(tenant_id: int, days: int = 30, db: AsyncSession = Depends(get_db)) -> dict:
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    if channel is None:
        raise HTTPException(404, "channel not found")
    await telegram_jobs.resync.defer_async(channel_id=channel.id, days=days)
    return {"ok": True}


@router.get("/tenants/{tenant_id}/checklist")
async def checklist(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Drives the onboarding wizard UI: which steps are done for this tenant."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    ok, dns_detail = verify_domain(tenant.domain)
    return {
        "tenant_id": tenant.id,
        "domain": tenant.domain,
        "status": tenant.status,
        "steps": {
            "channel": {
                "done": channel is not None,
                "title": channel.title if channel else None,
                "username": channel.username if channel else None,
                "total": channel.backfill_total_estimate if channel else None,
                "account_id": channel.telegram_account_id if channel else None,
                "noforwards": channel.noforwards if channel else None,
            },
            "bot": {"done": bool(tenant.bot_token_enc), "username": tenant.bot_username},
            "domain": {"done": tenant.domain_verified_at is not None, "detail": dns_detail, "resolves": ok},
            "backfill": {
                "done": channel is not None and channel.backfill_status == "done",
                "status": channel.backfill_status if channel else None,
                "checkpoint": channel.backfill_checkpoint if channel else 0,
                "total": channel.backfill_total_estimate if channel else None,
            },
        },
        "updated_at": datetime.now(UTC),
    }
