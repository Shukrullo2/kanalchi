"""Blogger studio API: ideas, drafts, uploads, publishing, voice and tag management.

Every route here requires a verified member of this tenant (`require_member`), which the auth layer
only grants after checking with Telegram that the signed-in account actually administers the channel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from procrastinate.exceptions import AlreadyEnqueued
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.auth import SessionData
from kanalchi.api.deps import enforce_same_origin, get_db, require_member, require_tenant
from kanalchi.core import storage
from kanalchi.core.jobs import create_job_run
from kanalchi.core.limits import get_budget
from kanalchi.core.logging import get_logger
from kanalchi.core.members import invite_member, list_members, remove_member
from kanalchi.core.models import (
    Channel,
    Draft,
    Idea,
    Post,
    TagCandidate,
    Tenant,
    TenantMember,
    Upload,
    UsageLedger,
)
from kanalchi.core.settings import get_settings
from kanalchi.jobs import publish_jobs
from kanalchi.telegram.formatting import DraftValidationError, length, validate, web_safe_html

log = get_logger(__name__)
router = APIRouter(
    prefix="/api/studio",
    tags=["studio"],
    dependencies=[Depends(require_member), Depends(enforce_same_origin)],
)

UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def _not_paused(tenant: Tenant) -> None:
    """Pausing a channel stops everything that spends: the assistant, rebuilds, imports."""
    if tenant.status == "paused":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "this channel is paused")


async def _set_idea_status(db: AsyncSession, draft: Draft, value: str) -> None:
    if draft.idea_id:
        idea = await db.get(Idea, draft.idea_id)
        if idea is not None and idea.status not in {"published", "dropped"}:
            idea.status = value


UPLOAD_KINDS = {
    "image/jpeg": "photo",
    "image/png": "photo",
    "image/webp": "photo",
    "video/mp4": "video",
    "video/quicktime": "video",
    "application/pdf": "document",
}


# --------------------------------------------------------------------- ideas
def idea_out(idea: Idea) -> dict[str, Any]:
    return {
        "id": idea.id,
        "title": idea.title,
        "body": idea.body,
        "status": idea.status,
        "position": idea.position,
        "related_post_ids": idea.related_post_ids or [],
        "created_at": idea.created_at,
    }


class IdeaIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=5000)
    status: str = Field(default="inbox", pattern="^(inbox|researching|drafting|scheduled|published|dropped)$")


class IdeaPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(
        default=None, pattern="^(inbox|researching|drafting|scheduled|published|dropped)$"
    )
    position: int | None = None


@router.get("/ideas")
async def list_ideas(
    tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Idea)
            .where(Idea.tenant_id == tenant.id)
            .order_by(Idea.status, Idea.position, Idea.id.desc())
        )
    ).all()
    return [idea_out(i) for i in rows]


@router.post("/ideas", status_code=201)
async def create_idea(
    body: IdeaIn,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    position = await db.scalar(
        select(func.coalesce(func.max(Idea.position), 0) + 1).where(
            Idea.tenant_id == tenant.id, Idea.status == body.status
        )
    )
    idea = Idea(
        tenant_id=tenant.id,
        user_id=user.user_id,
        title=body.title,
        body=body.body,
        status=body.status,
        position=position or 1,
    )
    db.add(idea)
    await db.flush()
    return idea_out(idea)


@router.patch("/ideas/{idea_id}")
async def patch_idea(
    idea_id: int,
    body: IdeaPatch,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    idea = await db.get(Idea, idea_id)
    if idea is None or idea.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "idea not found")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(idea, key, value)
    return idea_out(idea)


@router.delete("/ideas/{idea_id}")
async def delete_idea(
    idea_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    idea = await db.get(Idea, idea_id)
    if idea is None or idea.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "idea not found")
    await db.delete(idea)
    return {"ok": True}


# --------------------------------------------------------------------- drafts
def draft_out(draft: Draft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "idea_id": draft.idea_id,
        "title": draft.title,
        "html": draft.html,
        "media": draft.media or [],
        "status": draft.status,
        "scheduled_at": draft.scheduled_at,
        "published_tg_message_id": draft.published_tg_message_id,
        "published_at": draft.published_at,
        "publish_error": draft.publish_error,
        "disable_preview": bool(draft.disable_preview),
        "suggested_tags": draft.suggested_tags or [],
        "ai_generated": draft.ai_generated,
        "length": length(draft.html or ""),
        "updated_at": draft.updated_at,
    }


class DraftIn(BaseModel):
    html: str = Field(default="", max_length=20000)
    title: str = Field(default="", max_length=300)
    idea_id: int | None = None
    media: list[dict[str, Any]] = Field(default_factory=list)
    disable_preview: bool = False


class DraftPatch(BaseModel):
    html: str | None = Field(default=None, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    media: list[dict[str, Any]] | None = None
    disable_preview: bool | None = None


@router.get("/drafts")
async def list_drafts(
    status_filter: str | None = Query(default=None, alias="status"),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(Draft).where(Draft.tenant_id == tenant.id).order_by(Draft.updated_at.desc()).limit(100)
    if status_filter:
        stmt = stmt.where(Draft.status == status_filter)
    return [draft_out(d) for d in (await db.scalars(stmt)).all()]


@router.post("/drafts", status_code=201)
async def create_draft(
    body: DraftIn,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    draft = Draft(
        tenant_id=tenant.id,
        user_id=user.user_id,
        idea_id=body.idea_id,
        title=body.title,
        html=web_safe_html(body.html),
        media=body.media,
        disable_preview=body.disable_preview,
        status="draft",
    )
    db.add(draft)
    await db.flush()
    return draft_out(draft)


async def _get_draft(db: AsyncSession, tenant: Tenant, draft_id: int) -> Draft:
    draft = await db.get(Draft, draft_id)
    if draft is None or draft.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return draft


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    return draft_out(await _get_draft(db, tenant, draft_id))


@router.patch("/drafts/{draft_id}")
async def patch_draft(
    draft_id: int,
    body: DraftPatch,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    draft = await _get_draft(db, tenant, draft_id)
    if draft.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "a published post cannot be edited here")
    for key, value in body.model_dump(exclude_none=True).items():
        # The editor's markup is rendered back into the studio as HTML, so it is
        # scrubbed on the way in: an editor must not be able to plant a script that
        # runs in the owner's browser.
        setattr(draft, key, web_safe_html(value) if key == "html" else value)
    draft.status = "draft" if draft.status in {"failed", "canceled"} else draft.status
    return draft_out(draft)


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    draft = await _get_draft(db, tenant, draft_id)
    if draft.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "a published post cannot be deleted here")
    await db.delete(draft)
    return {"ok": True}


class ScheduleIn(BaseModel):
    scheduled_at: datetime | None = None


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: int,
    body: ScheduleIn,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    draft = await _get_draft(db, tenant, draft_id)
    if draft.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "this draft is already published")
    # Validate the draft first: a length problem is something the blogger can fix right now,
    # whereas a missing bot is for the platform admin to sort out.
    try:
        draft.html = validate(
            draft.html or "", has_media=bool(draft.media), media_count=len(draft.media or [])
        )
    except DraftValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if not tenant.bot_token_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this channel has no bot configured yet")

    when = body.scheduled_at
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    if when is not None and when <= datetime.now(UTC):
        when = None  # a time that has already passed means "now"

    draft.scheduled_at = when
    draft.status = "scheduled" if when else "publishing"
    draft.publish_error = None
    await _set_idea_status(db, draft, "scheduled" if when else "drafting")
    await db.flush()

    # A queued job cannot be withdrawn, so the job is told which schedule it serves and checks
    # the row when it fires; cancelling or moving the post simply leaves the old job with
    # nothing to do. The lock only folds two identical requests into one.
    slot = str(int(when.timestamp())) if when else "now"
    task = publish_jobs.publish.configure(
        queueing_lock=f"publish:{draft_id}:{slot}", **({"schedule_at": when} if when else {})
    )
    try:
        await task.defer_async(draft_id=draft_id, scheduled_at=when.isoformat() if when else None)
    except AlreadyEnqueued:
        pass  # the same send is already waiting; the row already says so
    return {"ok": True, "status": draft.status, "scheduled_at": when}


@router.post("/drafts/{draft_id}/cancel")
async def cancel_schedule(
    draft_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    draft = await _get_draft(db, tenant, draft_id)
    if draft.status not in {"scheduled", "failed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "only a scheduled or failed post can be cancelled")
    draft.status = "draft"
    draft.scheduled_at = None
    await _set_idea_status(db, draft, "drafting")
    return draft_out(draft)


# --------------------------------------------------------------------- uploads
@router.post("/uploads", status_code=201)
async def upload_media(
    file: UploadFile,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = get_settings()
    kind = UPLOAD_KINDS.get(file.content_type or "")
    if kind is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{file.content_type} is not supported")
    data = await file.read(UPLOAD_MAX_BYTES + 1)
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "files are limited to 50 MB")

    extension = (file.filename or "file").rsplit(".", 1)[-1][:8] or "bin"
    key = f"{tenant.id}/drafts/{uuid.uuid4().hex}.{extension}"
    await storage.upload_bytes(
        s.s3_bucket_uploads, key, data, file.content_type or "application/octet-stream"
    )

    upload = Upload(
        tenant_id=tenant.id,
        user_id=user.user_id,
        object_key=key,
        mime=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        kind=kind,
        status="ready",
    )
    db.add(upload)
    await db.flush()
    return {
        "upload_id": upload.id,
        "object_key": key,
        "kind": kind,
        "mime": upload.mime,
        "size_bytes": upload.size_bytes,
        "url": storage.public_presigned_url(await storage.presigned_get(s.s3_bucket_uploads, key)),
    }


# --------------------------------------------------------------------- AI assistance
class DraftAIIn(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)
    idea_id: int | None = None
    language: str | None = None
    length_hint: str | None = Field(default=None, max_length=60)


@router.post("/drafts/ai", status_code=201)
async def draft_with_ai(
    body: DraftAIIn,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from kanalchi.ai.drafting import draft_post, suggest_tags

    _not_paused(tenant)
    budget = await get_budget(
        tenant.id,
        "studio",
        float(tenant.daily_studio_budget_usd or get_settings().default_daily_studio_budget_usd),
    )
    if budget.exhausted:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "the studio is over its daily assistant budget"
        )

    try:
        result = await draft_post(tenant.id, body.brief, language=body.language, length_hint=body.length_hint)
    except Exception as exc:  # noqa: BLE001
        log.warning("studio.draft_ai_failed", tenant_id=tenant.id, error=str(exc)[:200])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "the assistant is unavailable right now"
        ) from exc
    if result.get("refused"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "the assistant declined this brief")

    from kanalchi.core.limits import add_spend

    await add_spend(tenant.id, "studio", float(result.get("cost_usd") or 0))

    draft = Draft(
        tenant_id=tenant.id,
        user_id=user.user_id,
        idea_id=body.idea_id,
        title=body.brief[:120],
        html=result["html"],
        media=[],
        status="draft",
        ai_generated=True,
        ai_prompt={"brief": body.brief, "context_post_ids": result.get("context_post_ids", [])},
        suggested_tags=await suggest_tags(tenant.id, result["html"]),
    )
    db.add(draft)
    await db.flush()
    return draft_out(draft)


@router.post("/drafts/{draft_id}/suggest-tags")
async def refresh_suggested_tags(
    draft_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    from kanalchi.ai.drafting import suggest_tags

    draft = await _get_draft(db, tenant, draft_id)
    draft.suggested_tags = await suggest_tags(tenant.id, draft.html or "")
    return draft_out(draft)


@router.post("/voice/rebuild")
async def rebuild_voice(tenant: Tenant = Depends(require_tenant)) -> dict:
    _not_paused(tenant)
    job_run_id = await create_job_run(tenant.id, "voice", {})
    await publish_jobs.build_voice.defer_async(tenant_id=tenant.id, job_run_id=job_run_id)
    return {"job_run_id": job_run_id}


# --------------------------------------------------------------------- dashboard
@router.get("/overview")
async def overview(tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)) -> dict:
    s = get_settings()
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
    posts = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
    )
    drafts = dict(
        (
            await db.execute(
                select(Draft.status, func.count()).where(Draft.tenant_id == tenant.id).group_by(Draft.status)
            )
        ).all()
    )
    ideas = dict(
        (
            await db.execute(
                select(Idea.status, func.count()).where(Idea.tenant_id == tenant.id).group_by(Idea.status)
            )
        ).all()
    )
    pending_tags = await db.scalar(
        select(func.count())
        .select_from(TagCandidate)
        .where(TagCandidate.tenant_id == tenant.id, TagCandidate.status == "pending", TagCandidate.count >= 3)
    )
    spend_today = await db.scalar(
        select(func.coalesce(func.sum(UsageLedger.cost_usd), 0)).where(
            UsageLedger.tenant_id == tenant.id, UsageLedger.day == func.current_date()
        )
    )
    budget = await get_budget(
        tenant.id, "studio", float(tenant.daily_studio_budget_usd or s.default_daily_studio_budget_usd)
    )
    return {
        "posts": posts or 0,
        "subscribers": channel.participants_count if channel else None,
        "drafts": drafts,
        "ideas": ideas,
        "pending_tags": pending_tags or 0,
        "spend_today_usd": float(spend_today or 0),
        "studio_budget_usd": budget.limit_usd,
        "studio_spent_usd": budget.spent_usd,
        "has_voice_profile": bool((tenant.settings or {}).get("voice_profile")),
        "bot_username": tenant.bot_username,
    }


# --------------------------------------------------------------------- members
class MemberIn(BaseModel):
    tg_user_id: int
    role: str = Field(default="editor", pattern="^(owner|editor)$")
    name: str | None = Field(default=None, max_length=128)


def _owner_only(user: SessionData) -> None:
    if user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can change the team")


@router.get("/members")
async def members(tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await list_members(db, tenant.id)


@router.post("/members", status_code=201)
async def add_member(
    body: MemberIn,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _owner_only(user)
    return await invite_member(db, tenant.id, body.tg_user_id, body.role, body.name)


@router.delete("/members/{tg_user_id}")
async def delete_member(
    tg_user_id: int,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _owner_only(user)
    if tg_user_id == user.tg_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "you cannot remove yourself")
    return {"removed": await remove_member(db, tenant.id, tg_user_id)}


# --------------------------------------------------------------------- settings
class StudioSettings(BaseModel):
    chat_enabled: bool | None = None
    chat_persona: str | None = Field(default=None, max_length=1000)
    theme: dict[str, Any] | None = None


@router.patch("/settings")
async def patch_settings(
    body: StudioSettings, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    row = await db.get(Tenant, tenant.id)
    row.settings = {**(row.settings or {}), **body.model_dump(exclude_none=True)}
    return {"settings": {k: v for k, v in row.settings.items() if k != "voice_profile"}}


@router.get("/settings")
async def get_studio_settings(
    tenant: Tenant = Depends(require_tenant),
    user: SessionData = Depends(require_member),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = tenant.settings or {}
    channel_username = await db.scalar(select(Channel.username).where(Channel.tenant_id == tenant.id))
    dm_chat_id = await db.scalar(
        select(TenantMember.dm_chat_id).where(
            TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.user_id
        )
    )
    return {
        "channel_username": channel_username,
        # Whether this member has pressed /start in the bot, which every notification needs.
        "notifications_linked": dm_chat_id is not None,
        "role": user.role,
        "paused": tenant.status == "paused",
        "chat_enabled": settings.get("chat_enabled", True),
        "chat_persona": settings.get("chat_persona"),
        "voice_profile": settings.get("voice_profile"),
        "channel_profile": settings.get("channel_profile"),
        "bot_username": tenant.bot_username,
        "webhook_ready": bool(tenant.bot_token_enc and tenant.webhook_secret),
        "locales": tenant.locales,
    }
