"""Platform admin API (admin host only)."""

from __future__ import annotations

import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import enforce_same_origin, get_db, require_admin
from kanalchi.core.jobs import create_job_run
from kanalchi.core.models import (
    Channel,
    JobRun,
    PlatformAdmin,
    TaxonomyVersion,
    TelegramAccount,
    Tenant,
    UsageLedger,
)
from kanalchi.core.settings import get_settings
from kanalchi.text.slug import slugify

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin), Depends(enforce_same_origin)]
)


def _tenant_out(t: Tenant, channel: Channel | None = None) -> dict:
    return {
        "id": t.id,
        "slug": t.slug,
        "domain": t.domain,
        "status": t.status,
        "title": t.title,
        "primary_lang": t.primary_lang,
        "locales": t.locales,
        "bot_username": t.bot_username,
        "has_bot_token": bool(t.bot_token_enc),
        "domain_verified_at": t.domain_verified_at,
        "daily_chat_budget_usd": float(t.daily_chat_budget_usd or 0),
        "daily_studio_budget_usd": float(t.daily_studio_budget_usd or 0),
        "created_at": t.created_at,
        "channel": {
            "id": channel.id,
            "tg_channel_id": channel.tg_channel_id,
            "username": channel.username,
            "title": channel.title,
            "backfill_status": channel.backfill_status,
            "backfill_checkpoint": channel.backfill_checkpoint,
            "backfill_total_estimate": channel.backfill_total_estimate,
            "participants_count": channel.participants_count,
        }
        if channel
        else None,
    }


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)) -> dict:
    tenants = (await db.scalars(select(Tenant).order_by(Tenant.created_at.desc()))).all()
    accounts = await db.scalar(select(func.count()).select_from(TelegramAccount))
    running = await db.scalar(select(func.count()).select_from(JobRun).where(JobRun.status == "running"))
    spend_today = await db.scalar(
        select(func.coalesce(func.sum(UsageLedger.cost_usd), 0)).where(UsageLedger.day == func.current_date())
    )
    return {
        "tenants": [_tenant_out(t) for t in tenants],
        "accounts": accounts or 0,
        "running_jobs": running or 0,
        "spend_today_usd": float(spend_today or 0),
    }


class TenantCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    title: str = Field(default="", max_length=255)
    slug: str | None = None
    primary_lang: str = "uz"


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = await db.execute(
        select(Tenant, Channel)
        .outerjoin(Channel, Channel.tenant_id == Tenant.id)
        .order_by(Tenant.created_at.desc())
    )
    return [_tenant_out(t, c) for t, c in rows.all()]


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreate, db: AsyncSession = Depends(get_db)) -> dict:
    domain = body.domain.lower().strip()
    if await db.scalar(select(Tenant.id).where(Tenant.domain == domain)):
        raise HTTPException(409, "domain already registered")
    slug = slugify(body.slug or domain.split(".")[0])
    if await db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        slug = f"{slug}-{secrets.token_hex(2)}"
    t = Tenant(
        domain=domain,
        slug=slug,
        title=body.title,
        primary_lang=body.primary_lang,
        webhook_secret=secrets.token_urlsafe(24),
    )
    db.add(t)
    await db.flush()
    return _tenant_out(t)


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(404, "tenant not found")
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    return _tenant_out(t, channel)


class TenantPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    primary_lang: str | None = None
    locales: list[str] | None = None
    daily_chat_budget_usd: float | None = None
    daily_studio_budget_usd: float | None = None


@router.patch("/tenants/{tenant_id}")
async def patch_tenant(tenant_id: int, body: TenantPatch, db: AsyncSession = Depends(get_db)) -> dict:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(404, "tenant not found")
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "status" and v not in {"active", "paused", "archived"}:
            raise HTTPException(400, "status must be active, paused or archived")
        setattr(t, k, v)
    from kanalchi.core.redis import get_redis

    await get_redis().delete(f"tenant:host:{t.domain}", f"tls:ask:{t.domain}")
    return _tenant_out(t)


@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.scalars(select(TelegramAccount).order_by(TelegramAccount.id))).all()
    return [
        {
            "id": a.id,
            "phone": a.phone,
            "display_name": a.display_name,
            "tg_user_id": a.tg_user_id,
            "status": a.status,
            "health": a.health,
            "last_seen_at": a.last_seen_at,
            "flood_wait_until": a.flood_wait_until,
        }
        for a in rows
    ]


@router.get("/jobs")
async def list_jobs(
    tenant_id: int | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    q = select(JobRun).order_by(JobRun.created_at.desc()).limit(min(limit, 500))
    if tenant_id:
        q = q.where(JobRun.tenant_id == tenant_id)
    rows = (await db.scalars(q)).all()
    return [
        {
            "id": j.id,
            "tenant_id": j.tenant_id,
            "type": j.type,
            "status": j.status,
            "progress": j.progress,
            "cost_usd": float(j.cost_usd or 0),
            "error": j.error,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "created_at": j.created_at,
        }
        for j in rows
    ]


class AdminAdd(BaseModel):
    tg_user_id: int
    note: str | None = None


@router.get("/admins")
async def list_admins(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.scalars(select(PlatformAdmin))).all()
    return [{"tg_user_id": a.tg_user_id, "note": a.note} for a in rows]


@router.post("/admins", status_code=201)
async def add_admin(body: AdminAdd, db: AsyncSession = Depends(get_db)) -> dict:
    if await db.get(PlatformAdmin, body.tg_user_id) is None:
        db.add(PlatformAdmin(tg_user_id=body.tg_user_id, note=body.note))
    return {"ok": True}


@router.delete("/admins/{tg_user_id}")
async def remove_admin(tg_user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(PlatformAdmin, tg_user_id)
    if row:
        await db.delete(row)
    return {"ok": True}


# --------------------------------------------------------------------- costs
@router.get("/costs")
async def costs(days: int = 30, db: AsyncSession = Depends(get_db)) -> dict:
    """Spend from the ledger, which is written from measured `usage`, never from estimates."""
    since = date.today() - timedelta(days=max(1, min(days, 365)))

    by_day = (
        await db.execute(
            select(
                UsageLedger.day,
                func.sum(UsageLedger.cost_usd),
                func.sum(UsageLedger.input_tokens + UsageLedger.cache_read_tokens),
                func.sum(UsageLedger.output_tokens),
            )
            .where(UsageLedger.day >= since)
            .group_by(UsageLedger.day)
            .order_by(UsageLedger.day)
        )
    ).all()

    by_purpose = (
        await db.execute(
            select(UsageLedger.purpose, func.sum(UsageLedger.cost_usd), func.sum(UsageLedger.requests))
            .where(UsageLedger.day >= since)
            .group_by(UsageLedger.purpose)
            .order_by(func.sum(UsageLedger.cost_usd).desc())
        )
    ).all()

    by_model = (
        await db.execute(
            select(UsageLedger.model, func.sum(UsageLedger.cost_usd), func.sum(UsageLedger.requests))
            .where(UsageLedger.day >= since)
            .group_by(UsageLedger.model)
            .order_by(func.sum(UsageLedger.cost_usd).desc())
        )
    ).all()

    by_tenant = (
        await db.execute(
            select(Tenant.id, Tenant.domain, func.sum(UsageLedger.cost_usd))
            .join(UsageLedger, UsageLedger.tenant_id == Tenant.id)
            .where(UsageLedger.day >= since)
            .group_by(Tenant.id, Tenant.domain)
            .order_by(func.sum(UsageLedger.cost_usd).desc())
            .limit(20)
        )
    ).all()

    cache_rows = (
        await db.execute(
            select(
                func.sum(UsageLedger.cache_read_tokens),
                func.sum(UsageLedger.input_tokens),
            ).where(UsageLedger.day >= since)
        )
    ).first()
    cache_read = int(cache_rows[0] or 0) if cache_rows else 0
    fresh_input = int(cache_rows[1] or 0) if cache_rows else 0
    total_input = cache_read + fresh_input

    return {
        "days": days,
        "total_usd": float(sum(float(r[1] or 0) for r in by_day)),
        "by_day": [
            {
                "day": d.isoformat(),
                "usd": float(usd or 0),
                "input_tokens": int(inp or 0),
                "output_tokens": int(out or 0),
            }
            for d, usd, inp, out in by_day
        ],
        "by_purpose": [
            {"purpose": p, "usd": float(u or 0), "requests": int(r or 0)} for p, u, r in by_purpose
        ],
        "by_model": [{"model": m, "usd": float(u or 0), "requests": int(r or 0)} for m, u, r in by_model],
        "by_tenant": [{"id": i, "domain": d, "usd": float(u or 0)} for i, d, u in by_tenant],
        # A high cache-read share is the single best sign the prompts are built correctly.
        "cache_hit_rate": round(cache_read / total_input, 3) if total_input else None,
        "platform_daily_cap_usd": get_settings().platform_daily_llm_cap_usd,
    }


# --------------------------------------------------------------------- tenant operations
@router.post("/tenants/{tenant_id}/reindex")
async def reindex(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Re-run extraction for everything that has no result yet, then rebuild the taxonomy."""
    from kanalchi.jobs import index_jobs

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    job_run_id = await create_job_run(tenant_id, "extract", {"trigger": "admin"})
    await index_jobs.index_backlog.defer_async(tenant_id=tenant_id, job_run_id=job_run_id)
    return {"job_run_id": job_run_id}


@router.get("/tenants/{tenant_id}/extract-estimate")
async def extract_estimate(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """What the next extraction batch will cost, measured on a sample rather than guessed."""
    from kanalchi.ai.extraction import estimate_cost

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    try:
        return await estimate_cost(tenant_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"cannot estimate right now: {type(exc).__name__}") from exc


@router.get("/tenants/{tenant_id}/taxonomy")
async def taxonomy_versions(tenant_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.scalars(
            select(TaxonomyVersion)
            .where(TaxonomyVersion.tenant_id == tenant_id)
            .order_by(TaxonomyVersion.version_no.desc())
            .limit(10)
        )
    ).all()
    return [
        {
            "id": v.id,
            "version_no": v.version_no,
            "status": v.status,
            "stats": v.candidate_stats,
            "diff": {k: (len(x) if isinstance(x, list) else x) for k, x in (v.diff or {}).items()},
            "cost_usd": float(v.cost_usd or 0),
            "built_at": v.built_at,
            "applied_at": v.applied_at,
        }
        for v in rows
    ]


@router.post("/tenants/{tenant_id}/taxonomy/{version_id}/apply")
async def apply_taxonomy_version(tenant_id: int, version_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    from kanalchi.jobs import index_jobs

    version = await db.get(TaxonomyVersion, version_id)
    if version is None or version.tenant_id != tenant_id:
        raise HTTPException(404, "taxonomy version not found")
    if version.status == "applied":
        raise HTTPException(409, "this version is already applied")
    job_run_id = await create_job_run(tenant_id, "taxonomy", {"version_id": version_id})
    await index_jobs.apply_taxonomy.defer_async(
        tenant_id=tenant_id, version_id=version_id, job_run_id=job_run_id
    )
    return {"job_run_id": job_run_id}
