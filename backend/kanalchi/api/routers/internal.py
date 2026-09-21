"""Internal-network endpoints: health, Caddy on-demand TLS gate, tenant lookup for the Next.js proxy."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db
from kanalchi.core import storage
from kanalchi.core.models import Tenant
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings

router = APIRouter(prefix="/internal", tags=["internal"])

_TLS_OK_STATUSES = {"backfilling", "indexing", "active", "paused"}


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    checks: dict[str, bool | str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception as exc:  # noqa: BLE001
        checks["db"] = f"error: {exc}"
    try:
        checks["redis"] = bool(await get_redis().ping())
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
    checks["minio"] = await storage.ping()
    r = get_redis()
    try:
        checks["worker_telegram"] = bool(await r.exists("hb:worker-telegram"))
        checks["worker_index"] = bool(await r.exists("hb:worker-index"))
    except Exception:  # noqa: BLE001
        pass
    core_ok = checks.get("db") is True and checks.get("redis") is True
    return {"ok": core_ok, "checks": checks}


@router.get("/tls/ask")
async def tls_ask(domain: str = Query(...), db: AsyncSession = Depends(get_db)) -> Response:
    """Caddy calls this before issuing a certificate. 200 = allowed, anything else = refused."""
    s = get_settings()
    domain = domain.lower().strip()
    if domain == s.admin_host:
        return Response(status_code=200)
    r = get_redis()
    cached = await r.get(f"tls:ask:{domain}")
    if cached is not None:
        return Response(status_code=200 if cached == "1" else 403)
    row = await db.execute(select(Tenant.status, Tenant.domain_verified_at).where(Tenant.domain == domain))
    rec = row.first()
    ok = bool(rec and rec.status in _TLS_OK_STATUSES and rec.domain_verified_at is not None)
    if s.is_dev and rec is not None:
        ok = True  # local dev uses Caddy's internal CA anyway
    await r.set(f"tls:ask:{domain}", "1" if ok else "0", ex=60)
    return Response(status_code=200 if ok else 403)


@router.get("/tenants/by-host")
async def tenant_by_host(host: str = Query(...), db: AsyncSession = Depends(get_db)) -> dict:
    """Used by the Next.js proxy to rewrite tenant domains. Public tenant info only."""
    host = host.split(":")[0].lower()
    t = await db.scalar(select(Tenant).where(Tenant.domain == host))
    if t is None or t.status == "archived":
        raise HTTPException(404, "unknown host")
    return {
        "id": t.id,
        "slug": t.slug,
        "domain": t.domain,
        "status": t.status,
        "title": t.title,
        "primary_lang": t.primary_lang,
        "locales": t.locales,
        "bot_username": t.bot_username,
        "theme": (t.settings or {}).get("theme", {}),
    }
