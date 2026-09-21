"""Telegram Bot API webhooks, one path per tenant."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, Update
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db
from kanalchi.core.crypto import decrypt
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Tenant, TenantMember, User
from kanalchi.core.settings import get_settings

log = get_logger(__name__)
router = APIRouter(prefix="/tg", tags=["telegram-bot"])

_bots: dict[int, tuple[str, Bot]] = {}
_dp = Dispatcher()
_r = Router()
_dp.include_router(_r)


def tenant_bot(tenant: Tenant) -> Bot:
    token = decrypt(tenant.bot_token_enc)
    cached = _bots.get(tenant.id)
    if cached and cached[0] == token:
        return cached[1]
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _bots[tenant.id] = (token, bot)
    return bot


@_r.message(CommandStart())
async def on_start(message: Message, tenant: Tenant, db: AsyncSession) -> None:
    s = get_settings()
    tg_id = message.from_user.id if message.from_user else None
    user = await db.scalar(select(User).where(User.tg_user_id == tg_id)) if tg_id else None
    member = None
    if user:
        member = await db.scalar(
            select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.id)
        )
    if member:
        member.dm_chat_id = message.chat.id
        member.updated_at = datetime.now(UTC)
        await message.answer(
            f"Salom! Bu <b>{tenant.title}</b> studiyasining boti. Nashr va xabarnomalar shu yerga keladi.\n{s.public_url(tenant.domain, '/studio')}"
        )
    else:
        await message.answer(f"<b>{tenant.title}</b> — {s.public_url(tenant.domain)}")


@router.post("/webhook/{tenant_id}/{secret}", include_in_schema=False)
async def webhook(
    tenant_id: int,
    secret: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    header_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or not tenant.bot_token_enc or not tenant.webhook_secret:
        raise HTTPException(404)
    if secret != tenant.webhook_secret or header_secret != tenant.webhook_secret:
        raise HTTPException(403)
    payload = await request.json()
    bot = tenant_bot(tenant)
    try:
        update = Update.model_validate(payload, context={"bot": bot})
        await _dp.feed_update(bot, update, tenant=tenant, db=db)
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook.failed", tenant_id=tenant_id, error=str(exc))
    return {"ok": True}
