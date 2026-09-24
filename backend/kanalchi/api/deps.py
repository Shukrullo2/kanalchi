"""FastAPI dependencies: db session, tenant resolution from Host, current user and role guards."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.auth import SESSION_COOKIE, SessionData, load_session
from kanalchi.core.db import get_sessionmaker
from kanalchi.core.models import Tenant
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import Settings, get_settings


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def get_config() -> Settings:
    return get_settings()


def request_host(request: Request) -> str:
    """Tenant host: internal header from the Next.js server, else the browser's Host (Caddy keeps it)."""
    host = request.headers.get("x-tenant-host") or request.headers.get("host") or ""
    return host.split(":")[0].lower().strip()


@dataclass(slots=True)
class TenantContext:
    host: str
    is_admin_host: bool
    tenant: Tenant | None
    # The platform's own domain: the landing page and the self-serve sign-up live there.
    is_platform_host: bool = False

    @property
    def tenant_id(self) -> int | None:
        return self.tenant.id if self.tenant else None


async def _tenant_id_for_host(host: str, db: AsyncSession) -> int | None:
    r = get_redis()
    cached = await r.get(f"tenant:host:{host}")
    if cached is not None:
        return int(cached) if cached != "0" else None
    tid = await db.scalar(select(Tenant.id).where(Tenant.domain == host))
    await r.set(f"tenant:host:{host}", str(tid or 0), ex=60)
    return tid


async def get_tenant_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> TenantContext:
    s = get_settings()
    host = request_host(request)
    if host == s.admin_host:
        return TenantContext(host=host, is_admin_host=True, tenant=None)
    tid = await _tenant_id_for_host(host, db)
    if tid is None:
        # A registered channel domain always wins over the platform domain (proxy.ts agrees).
        if host in s.platform_hosts:
            return TenantContext(host=host, is_admin_host=False, tenant=None, is_platform_host=True)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown host")
    tenant = await db.get(Tenant, tid)
    if tenant is None or tenant.status == "archived":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown host")
    return TenantContext(host=host, is_admin_host=False, tenant=tenant)


async def require_tenant(ctx: TenantContext = Depends(get_tenant_ctx)) -> Tenant:
    if ctx.tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="tenant route on admin host")
    return ctx.tenant


async def current_user(request: Request) -> SessionData | None:
    return await load_session(request.cookies.get(SESSION_COOKIE))


async def require_admin(
    user: SessionData | None = Depends(current_user), ctx: TenantContext = Depends(get_tenant_ctx)
) -> SessionData:
    if user is None or user.role != "admin" or not ctx.is_admin_host:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin only")
    return user


async def require_member(
    user: SessionData | None = Depends(current_user), ctx: TenantContext = Depends(get_tenant_ctx)
) -> SessionData:
    """Blogger studio: owner or editor of *this* tenant."""
    if (
        user is None
        or ctx.tenant is None
        or user.tenant_id != ctx.tenant.id
        or user.role not in {"owner", "editor"}
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="studio members only")
    return user


async def require_user(
    user: SessionData | None = Depends(current_user), ctx: TenantContext = Depends(get_tenant_ctx)
) -> SessionData:
    """Self-serve sign-up: anyone signed in through Telegram on the platform domain."""
    if user is None or user.role != "user" or not ctx.is_platform_host:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="sign in first")
    return user


def enforce_same_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated mutations (SameSite=Lax + Origin check)."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if not origin:
        return  # non-browser clients (no Origin) are not cookie-authenticated in practice
    host = request_host(request)
    if origin.split("://", 1)[-1].split(":")[0].lower() != host:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="cross-origin request rejected")


def json_dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
