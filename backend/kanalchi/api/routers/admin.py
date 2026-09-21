"""Platform admin API (admin host only)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import enforce_same_origin, get_db, require_admin
from kanalchi.core.models import Channel, JobRun, PlatformAdmin, TelegramAccount, Tenant, UsageLedger
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
