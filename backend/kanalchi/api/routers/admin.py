"""Platform admin API (admin host only)."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.ai import tagops
from kanalchi.api.deps import enforce_same_origin, get_db, require_admin
from kanalchi.api.routers.tags import tag_out
from kanalchi.core import billing
from kanalchi.core.jobs import create_job_run
from kanalchi.core.members import invite_member, list_members, remove_member
from kanalchi.core.models import (
    Channel,
    Dimension,
    JobRun,
    PlatformAdmin,
    Post,
    Tag,
    TaxonomyVersion,
    TelegramAccount,
    Tenant,
    UsageLedger,
    User,
)
from kanalchi.core.settings import get_settings
from kanalchi.text.slug import slugify

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin), Depends(enforce_same_origin)]
)


async def _imported(db: AsyncSession, channel_ids: list[int]) -> dict[int, int]:
    """Posts actually stored per channel. The backfill checkpoint is a Telegram message id, which
    skips deleted and service messages, so it cannot stand in for a count."""
    if not channel_ids:
        return {}
    rows = await db.execute(
        select(Post.channel_id, func.count())
        .where(Post.channel_id.in_(channel_ids))
        .group_by(Post.channel_id)
    )
    return dict(rows.all())


def _tenant_out(t: Tenant, channel: Channel | None = None, imported: int = 0) -> dict:
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
        # Given a placeholder under the platform domain rather than a domain of its own.
        "auto_domain": bool((t.settings or {}).get("auto_domain")),
        "daily_chat_budget_usd": float(t.daily_chat_budget_usd or 0),
        "daily_studio_budget_usd": float(t.daily_studio_budget_usd or 0),
        "created_at": t.created_at,
        # Self-serve sign-up and billing; admin-created channels are "admin" with no owner.
        "source": t.source,
        "owner_user_id": t.owner_user_id,
        "plan": t.plan,
        "subscription_status": t.subscription_status,
        "subscription_paid_until": t.subscription_paid_until,
        "onboarding_quote": t.onboarding_quote,
        "onboarding_paid_at": t.onboarding_paid_at,
        "requested_at": ((t.settings or {}).get("signup") or {}).get("requested_at"),
        "verify_skipped": bool(((t.settings or {}).get("signup") or {}).get("verify_skipped")),
        "channel": {
            "id": channel.id,
            "tg_channel_id": channel.tg_channel_id,
            "username": channel.username,
            "title": channel.title,
            "backfill_status": channel.backfill_status,
            "backfill_checkpoint": channel.backfill_checkpoint,
            "backfill_total_estimate": channel.backfill_total_estimate,
            "imported": imported,
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
    # Optional: without one the channel lives at <slug>.<platform domain> until one is set.
    domain: str | None = Field(default=None, min_length=3, max_length=253)
    title: str = Field(default="", max_length=255)
    slug: str | None = None
    primary_lang: str = "uz"
    # Optional: the blogger's Telegram id, so they can sign in before (or without) a bot.
    owner_tg_id: int | None = None
    owner_name: str | None = Field(default=None, max_length=128)


def _clean_domain(value: str) -> str:
    domain = value.lower().strip().strip(".")
    if "/" in domain or " " in domain or "." not in domain:
        raise HTTPException(400, "that does not look like a domain name")
    return domain


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(
            select(Tenant, Channel)
            .outerjoin(Channel, Channel.tenant_id == Tenant.id)
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    imported = await _imported(db, [c.id for _, c in rows if c is not None])
    return [_tenant_out(t, c, imported.get(c.id, 0) if c else 0) for t, c in rows]


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreate, db: AsyncSession = Depends(get_db)) -> dict:
    s = get_settings()
    auto = body.domain is None
    slug = slugify(body.slug or (body.domain.split(".")[0] if body.domain else body.title) or "")
    slug = slug or f"channel-{secrets.token_hex(3)}"
    if await db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        slug = f"{slug}-{secrets.token_hex(2)}"
    domain = f"{slug}.{s.tenant_base_domain}" if auto else _clean_domain(body.domain or "")
    if await db.scalar(select(Tenant.id).where(Tenant.domain == domain)):
        raise HTTPException(409, "domain already registered")
    t = Tenant(
        domain=domain,
        slug=slug,
        title=body.title,
        primary_lang=body.primary_lang,
        webhook_secret=secrets.token_urlsafe(24),
        settings={"auto_domain": True} if auto else {},
        # The platform domain's wildcard record already points here; only a custom domain needs checking.
        domain_verified_at=datetime.now(UTC) if auto else None,
    )
    db.add(t)
    await db.flush()
    if body.owner_tg_id:
        await invite_member(db, t.id, body.owner_tg_id, "owner", body.owner_name)
    return _tenant_out(t)


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(404, "tenant not found")
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    imported = (await _imported(db, [channel.id]))[channel.id] if channel else 0
    return _tenant_out(t, channel, imported if channel else 0)


class TenantPatch(BaseModel):
    title: str | None = None
    domain: str | None = Field(default=None, min_length=3, max_length=253)
    status: str | None = None
    primary_lang: str | None = None
    locales: list[str] | None = None
    daily_chat_budget_usd: float | None = None
    daily_studio_budget_usd: float | None = None
    plan: str | None = Field(default=None, pattern="^(archive|basic|premium)$")
    subscription_status: str | None = Field(
        default=None, pattern="^(none|pending|active|past_due|cancelled)$"
    )
    subscription_paid_until: date | None = None
    # True stamps now, False clears it; None leaves it alone.
    onboarding_paid: bool | None = None


@router.patch("/tenants/{tenant_id}")
async def patch_tenant(tenant_id: int, body: TenantPatch, db: AsyncSession = Depends(get_db)) -> dict:
    t = await db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(404, "tenant not found")
    from kanalchi.core.redis import get_redis

    old_domain = t.domain
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "onboarding_paid":
            t.onboarding_paid_at = datetime.now(UTC) if v else None
            continue
        if k == "status" and v not in {"active", "paused", "archived"}:
            raise HTTPException(400, "status must be active, paused or archived")
        if k == "domain":
            v = _clean_domain(v)
            if v != t.domain and await db.scalar(select(Tenant.id).where(Tenant.domain == v)):
                raise HTTPException(409, "domain already registered")
            if v != t.domain:
                # A domain of its own has to be pointed at the server and checked; the
                # placeholder under the platform domain never did.
                t.settings = {**(t.settings or {}), "auto_domain": False}
                t.domain_verified_at = None
        setattr(t, k, v)
    await get_redis().delete(
        f"tenant:host:{old_domain}", f"tls:ask:{old_domain}", f"tenant:host:{t.domain}", f"tls:ask:{t.domain}"
    )
    return _tenant_out(t)


# --------------------------------------------------------------------- sign-ups
@router.get("/signups")
async def signups(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Everyone who signed in on the platform domain, newest first, with the channels they added."""
    users = (
        await db.scalars(
            select(User).where(User.signed_up_at.is_not(None)).order_by(User.signed_up_at.desc())
        )
    ).all()
    rows = (
        await db.execute(
            select(Tenant, Channel)
            .outerjoin(Channel, Channel.tenant_id == Tenant.id)
            .where(Tenant.owner_user_id.in_([u.id for u in users]) if users else False)
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    imported = await _imported(db, [c.id for _, c in rows if c is not None])
    by_owner: dict[int, list[dict]] = {}
    for t, c in rows:
        by_owner.setdefault(t.owner_user_id or 0, []).append(
            _tenant_out(t, c, imported.get(c.id, 0) if c else 0)
        )
    return [
        {
            "user_id": u.id,
            "tg_user_id": u.tg_user_id,
            "name": " ".join(x for x in [u.first_name, u.last_name] if x) or u.username or str(u.tg_user_id),
            "username": u.username,
            "photo_url": u.photo_url,
            "signed_up_at": u.signed_up_at,
            "last_login_at": u.last_login_at,
            "tenants": by_owner.get(u.id, []),
        }
        for u in users
    ]


@router.get("/plans")
async def admin_plans() -> dict:
    return {"plans": billing.plan_catalogue(), "statuses": list(billing.SUBSCRIPTION_STATUSES)}


# --------------------------------------------------------------------- members
class MemberIn(BaseModel):
    tg_user_id: int
    role: str = Field(default="owner", pattern="^(owner|editor)$")
    name: str | None = Field(default=None, max_length=128)


@router.get("/tenants/{tenant_id}/members")
async def tenant_members(tenant_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await list_members(db, tenant_id)


@router.post("/tenants/{tenant_id}/members", status_code=201)
async def add_tenant_member(tenant_id: int, body: MemberIn, db: AsyncSession = Depends(get_db)) -> dict:
    if await db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, "tenant not found")
    return await invite_member(db, tenant_id, body.tg_user_id, body.role, body.name)


@router.delete("/tenants/{tenant_id}/members/{tg_user_id}")
async def remove_tenant_member(tenant_id: int, tg_user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    return {"removed": await remove_member(db, tenant_id, tg_user_id)}


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
    q = (
        select(JobRun, Tenant.domain)
        .outerjoin(Tenant, Tenant.id == JobRun.tenant_id)
        .order_by(JobRun.created_at.desc())
        .limit(min(limit, 500))
    )
    if tenant_id:
        q = q.where(JobRun.tenant_id == tenant_id)
    rows = (await db.execute(q)).all()
    return [
        {
            "id": j.id,
            "tenant_id": j.tenant_id,
            "tenant_domain": domain,
            "type": j.type,
            "status": j.status,
            "progress": j.progress,
            "cost_usd": float(j.cost_usd or 0),
            "error": j.error,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "created_at": j.created_at,
        }
        for j, domain in rows
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


# --------------------------------------------------------------------- index (tags)
def _tenant_or_404(t: Tenant | None) -> Tenant:
    if t is None:
        raise HTTPException(404, "tenant not found")
    return t


@router.get("/tenants/{tenant_id}/dimensions")
async def tenant_dimensions(tenant_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.scalars(
            select(Dimension)
            .where(Dimension.tenant_id == tenant_id, Dimension.is_visible.is_(True))
            .order_by(Dimension.sort_order)
        )
    ).all()
    return [{"key": d.key, "labels": d.labels or {}, "kind": d.kind} for d in rows]


@router.get("/tenants/{tenant_id}/tags")
async def tenant_tags(
    tenant_id: int, limit: int = Query(300, ge=1, le=1000), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """The live index: active tags with posts, most-used first."""
    rows = (
        await db.execute(
            select(Tag, Dimension.key)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(Tag.tenant_id == tenant_id, Tag.status == "active", Tag.post_count > 0)
            .order_by(Tag.post_count.desc())
            .limit(limit)
        )
    ).all()
    return [tag_out(t, key) for t, key in rows]


@router.get("/tenants/{tenant_id}/tags/pending")
async def tenant_pending_tags(
    tenant_id: int, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await tagops.pending_candidates(db, tenant_id, limit)


@router.get("/tenants/{tenant_id}/tags/hidden")
async def tenant_hidden_tags(tenant_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    return [tag_out(t, key) for t, key in await tagops.hidden_tags(db, tenant_id)]


class TagEdit(BaseModel):
    labels: dict[str, str] | None = None
    descriptions: dict[str, str] | None = None
    hidden: bool | None = None


class TagMerge(BaseModel):
    into: str = Field(min_length=1, max_length=96)


def _op(exc: tagops.TagOpError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


@router.patch("/tenants/{tenant_id}/tags/{slug}")
async def tenant_edit_tag(
    tenant_id: int, slug: str, body: TagEdit, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await tagops.edit_tag(
            db, tenant_id, slug, labels=body.labels, descriptions=body.descriptions, hidden=body.hidden
        )
    except tagops.TagOpError as exc:
        raise _op(exc) from exc


@router.post("/tenants/{tenant_id}/tags/{slug}/merge")
async def tenant_merge_tag(
    tenant_id: int, slug: str, body: TagMerge, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await tagops.merge_tag(db, tenant_id, slug, body.into)
    except tagops.TagOpError as exc:
        raise _op(exc) from exc


@router.post("/tenants/{tenant_id}/tags/pending/{candidate_id}/promote")
async def tenant_promote_candidate(
    tenant_id: int, candidate_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await tagops.promote_candidate(db, tenant_id, candidate_id)
    except tagops.TagOpError as exc:
        raise _op(exc) from exc


@router.post("/tenants/{tenant_id}/tags/pending/{candidate_id}/reject")
async def tenant_reject_candidate(
    tenant_id: int, candidate_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await tagops.reject_candidate(db, tenant_id, candidate_id)
    except tagops.TagOpError as exc:
        raise _op(exc) from exc


@router.post("/tenants/{tenant_id}/taxonomy/rebuild")
async def tenant_rebuild_taxonomy(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    tenant = _tenant_or_404(await db.get(Tenant, tenant_id))
    if tenant.status == "paused":
        raise HTTPException(409, "the channel is paused")
    try:
        return await tagops.request_rebuild(tenant_id, trigger="admin")
    except tagops.TagOpError as exc:
        raise _op(exc) from exc


# --------------------------------------------------------------------- costs
@router.get("/costs")
async def costs(days: int = 30, db: AsyncSession = Depends(get_db)) -> dict:
    """Spend from the ledger, which is written from measured `usage`, never from estimates."""
    today = datetime.now(UTC).date()  # ledger days are UTC; the server's local date is not
    since = today - timedelta(days=max(1, min(days, 365)))

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

    # One entry per calendar day from the first spend to today, quiet days included, so the
    # chart is a timeline rather than a list of busy days pushed together.
    spent = {d: (usd, inp, out) for d, usd, inp, out in by_day}
    timeline: list[dict] = []
    if spent:
        day = max(since, min(spent))
        while day <= today:
            usd, inp, out = spent.get(day, (0, 0, 0))
            timeline.append(
                {
                    "day": day.isoformat(),
                    "usd": float(usd or 0),
                    "input_tokens": int(inp or 0),
                    "output_tokens": int(out or 0),
                }
            )
            day += timedelta(days=1)

    return {
        "days": days,
        "total_usd": float(sum(float(r[1] or 0) for r in by_day)),
        "by_day": timeline,
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


@router.get("/tenants/{tenant_id}/estimate")
async def pipeline_estimate(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """What finishing this channel will cost, before the import starts and as it goes."""
    from kanalchi.jobs.pipeline import estimate

    if await db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, "tenant not found")
    return await estimate(tenant_id)


@router.post("/tenants/{tenant_id}/pipeline/reconcile")
async def pipeline_reconcile(tenant_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Queue whatever step the pipeline is missing. Safe to press any number of times."""
    from kanalchi.jobs.pipeline import reconcile

    if await db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, "tenant not found")
    return {"actions": await reconcile(tenant_id, force=True)}


@router.get("/tenants/{tenant_id}/taxonomy/{version_id}")
async def taxonomy_version_preview(tenant_id: int, version_id: int) -> dict:
    from kanalchi.ai.taxonomy import preview

    try:
        return await preview(tenant_id, version_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc


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
