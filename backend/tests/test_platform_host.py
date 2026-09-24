"""The platform domain is a host of its own: no tenant, sign-up allowed, admin and studio roles rejected."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from kanalchi.api.auth import SessionData
from kanalchi.api.deps import TenantContext, require_admin, require_member, require_user
from kanalchi.core.settings import get_settings


def _user(role: str) -> SessionData:
    return SessionData(user_id=1, tg_user_id=1, role=role, tenant_id=None, name="x")


def test_platform_hosts_include_the_dev_stand_in() -> None:
    s = get_settings()
    assert s.is_dev
    assert "osor.localhost" in s.platform_hosts


async def test_require_user_only_on_platform_host() -> None:
    platform = TenantContext(host="osor.localhost", is_admin_host=False, tenant=None, is_platform_host=True)
    admin_host = TenantContext(host="admin.localhost", is_admin_host=True, tenant=None)
    assert (await require_user(_user("user"), platform)).role == "user"
    with pytest.raises(HTTPException):
        await require_user(_user("admin"), platform)
    with pytest.raises(HTTPException):
        await require_user(_user("user"), admin_host)
    with pytest.raises(HTTPException):
        await require_user(None, platform)


async def test_platform_session_opens_nothing_else() -> None:
    platform = TenantContext(host="osor.localhost", is_admin_host=False, tenant=None, is_platform_host=True)
    tenant_ctx = TenantContext(host="x.osor.localhost", is_admin_host=False, tenant=SimpleNamespace(id=5))  # type: ignore[arg-type]
    with pytest.raises(HTTPException):
        await require_admin(_user("user"), platform)
    with pytest.raises(HTTPException):
        await require_member(_user("user"), tenant_ctx)
