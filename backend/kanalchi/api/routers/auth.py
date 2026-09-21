"""Telegram Login Widget sign-in for admins (admin host) and bloggers (tenant hosts)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.auth import (
    SESSION_COOKIE,
    SessionData,
    create_session,
    destroy_session,
    verify_telegram_login,
)
from kanalchi.api.deps import TenantContext, current_user, get_db, get_tenant_ctx
from kanalchi.core.crypto import decrypt
from kanalchi.core.models import PlatformAdmin, TenantMember, User
from kanalchi.core.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


@router.get("/widget")
async def widget_info(ctx: TenantContext = Depends(get_tenant_ctx)) -> dict:
    """Which bot the Login Widget on this host must use."""
    s = get_settings()
    if ctx.is_admin_host:
        bot = None
        if s.platform_bot_token:
            bot = (await _bot_username(s.platform_bot_token)) or None
        return {"mode": "admin", "bot_username": bot}
    return {"mode": "studio", "bot_username": ctx.tenant.bot_username if ctx.tenant else None}


async def _bot_username(token: str) -> str | None:
    from aiogram import Bot

    try:
        async with Bot(token) as bot:
            me = await bot.get_me()
            return me.username
    except Exception:  # noqa: BLE001
        return None


@router.post("/telegram")
async def telegram_login(
    payload: TelegramLoginPayload,
    response: Response,
    ctx: TenantContext = Depends(get_tenant_ctx),
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = get_settings()
    if ctx.is_admin_host:
        bot_token = s.platform_bot_token
    else:
        bot_token = decrypt(ctx.tenant.bot_token_enc) if ctx.tenant and ctx.tenant.bot_token_enc else None
    if not bot_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="login bot not configured for this host"
        )
    if not verify_telegram_login(payload.model_dump(), bot_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid telegram login")

    now = datetime.now(UTC)
    stmt = insert(User).values(
        tg_user_id=payload.id,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        photo_url=payload.photo_url,
        last_login_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.tg_user_id],
        set_={
            "username": payload.username,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "photo_url": payload.photo_url,
            "last_login_at": now,
        },
    ).returning(User.id)
    user_id = await db.scalar(stmt)
    name = " ".join(x for x in [payload.first_name, payload.last_name] if x) or (
        payload.username or str(payload.id)
    )

    if ctx.is_admin_host:
        allowed = payload.id in s.admin_tg_ids or (await db.get(PlatformAdmin, payload.id)) is not None
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="not a platform admin")
        role, tenant_id = "admin", None
    else:
        assert ctx.tenant is not None
        member = await db.scalar(
            select(TenantMember).where(
                TenantMember.tenant_id == ctx.tenant.id, TenantMember.user_id == user_id
            )
        )
        fresh = (
            member is not None
            and member.verified_admin_at is not None
            and member.verified_admin_at > now - timedelta(days=7)
        )
        if not fresh:
            from kanalchi.telegram.verify import is_channel_admin

            channel = ctx.tenant.channel
            ok = channel is not None and await is_channel_admin(bot_token, channel.tg_channel_id, payload.id)
            if not ok:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="you are not an admin of this channel")
            if member is None:
                member = TenantMember(tenant_id=ctx.tenant.id, user_id=user_id, role="owner")
                db.add(member)
            member.verified_admin_at = now
        role, tenant_id = member.role, ctx.tenant.id

    cookie = await create_session(
        SessionData(
            user_id=user_id,
            tg_user_id=payload.id,
            role=role,
            tenant_id=tenant_id,
            name=name,
            username=payload.username,
            photo_url=payload.photo_url,
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=s.session_ttl_days * 86400,
        httponly=True,
        secure=not s.is_dev,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "role": role, "name": name}


class DevLogin(BaseModel):
    tg_user_id: int
    name: str = "Dev User"


@router.post("/dev-login", include_in_schema=False)
async def dev_login(
    body: DevLogin,
    response: Response,
    ctx: TenantContext = Depends(get_tenant_ctx),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Local development only: mint a session without Telegram (admin on the admin host, owner on a tenant host)."""
    s = get_settings()
    if not s.is_dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    stmt = insert(User).values(
        tg_user_id=body.tg_user_id, first_name=body.name, last_login_at=datetime.now(UTC)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.tg_user_id], set_={"last_login_at": datetime.now(UTC)}
    ).returning(User.id)
    user_id = await db.scalar(stmt)
    if ctx.is_admin_host:
        role, tenant_id = "admin", None
    else:
        assert ctx.tenant is not None
        member = await db.scalar(
            select(TenantMember).where(
                TenantMember.tenant_id == ctx.tenant.id, TenantMember.user_id == user_id
            )
        )
        if member is None:
            db.add(
                TenantMember(
                    tenant_id=ctx.tenant.id,
                    user_id=user_id,
                    role="owner",
                    verified_admin_at=datetime.now(UTC),
                )
            )
        role, tenant_id = "owner", ctx.tenant.id
    cookie = await create_session(
        SessionData(
            user_id=user_id, tg_user_id=body.tg_user_id, role=role, tenant_id=tenant_id, name=body.name
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=s.session_ttl_days * 86400,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "role": role, "name": body.name}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    await destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(
    user: SessionData | None = Depends(current_user), ctx: TenantContext = Depends(get_tenant_ctx)
) -> dict:
    if user is None:
        return {"authenticated": False}
    # A session minted on another host must not leak roles across domains.
    if ctx.is_admin_host and user.role != "admin":
        return {"authenticated": False}
    if not ctx.is_admin_host and (ctx.tenant is None or user.tenant_id != ctx.tenant.id):
        return {"authenticated": False}
    return {
        "authenticated": True,
        "role": user.role,
        "name": user.name,
        "username": user.username,
        "photo_url": user.photo_url,
        "tg_user_id": user.tg_user_id,
    }
