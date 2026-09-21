"""Tenant scoping helpers. Any query against a tenant-owned model must go through `scoped()`."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select


class TenantScopeError(RuntimeError):
    pass


def scoped(model: Any, tenant_id: int | None) -> Select:
    """`select(model)` with the tenant filter applied; refuses to build unscoped queries."""
    if not hasattr(model, "tenant_id"):
        raise TenantScopeError(f"{model.__name__} is not tenant-scoped; use select() directly")
    if tenant_id is None:
        raise TenantScopeError(f"tenant_id required to query {model.__name__}")
    return select(model).where(model.tenant_id == tenant_id)
