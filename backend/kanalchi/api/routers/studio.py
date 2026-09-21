"""Blogger studio API: ideas, drafts, uploads, publishing, voice and tag management.

Every route here requires a verified member of this tenant (`require_member`), which the auth layer
only grants after checking with Telegram that the signed-in account actually administers the channel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.auth import SessionData
from kanalchi.api.deps import enforce_same_origin, get_db, require_member, require_tenant
from kanalchi.core import storage
from kanalchi.core.jobs import create_job_run
from kanalchi.core.limits import get_budget
from kanalchi.core.logging import get_logger
from kanalchi.core.models import (
    Channel,
    Dimension,
    Draft,
    Idea,
    Post,
    PostTag,
    Tag,
    TagAlias,
    TagCandidate,
    Tenant,
    Upload,
    UsageLedger,
)
from kanalchi.core.settings import get_settings
from kanalchi.jobs import index_jobs, publish_jobs
from kanalchi.telegram.formatting import DraftValidationError, length, validate

log = get_logger(__name__)
router = APIRouter(
    prefix="/api/studio",
    tags=["studio"],
    dependencies=[Depends(require_member), Depends(enforce_same_origin)],
)

UPLOAD_MAX_BYTES = 50 * 1024 * 1024
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
        html=body.html,
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
        setattr(draft, key, value)
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
    await db.flush()

    task = publish_jobs.publish.configure(
        queueing_lock=f"publish:{draft_id}", **({"schedule_at": when} if when else {})
    )
    await task.defer_async(draft_id=draft_id)
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
        "url": await storage.presigned_get(s.s3_bucket_uploads, key),
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
    return {"suggested_tags": draft.suggested_tags}


@router.post("/voice/rebuild")
async def rebuild_voice(tenant: Tenant = Depends(require_tenant)) -> dict:
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


# --------------------------------------------------------------------- tag management
@router.get("/tags/pending")
async def pending_tags(
    limit: int = Query(50, ge=1, le=200),
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        await db.execute(
            select(TagCandidate, Dimension.key)
            .join(Dimension, Dimension.id == TagCandidate.dimension_id)
            .where(TagCandidate.tenant_id == tenant.id, TagCandidate.status == "pending")
            .order_by(TagCandidate.count.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "dimension": key,
            "count": c.count,
            "surface_forms": c.surface_forms or [],
            "sample_post_ids": c.sample_post_ids or [],
        }
        for c, key in rows
    ]


class TagEdit(BaseModel):
    labels: dict[str, str] | None = None
    description: str | None = Field(default=None, max_length=500)
    hidden: bool | None = None


@router.patch("/tags/{slug}")
async def edit_tag(
    slug: str,
    body: TagEdit,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A manual edit pins the tag, which is what makes it survive the next taxonomy rebuild."""
    tag = await db.scalar(select(Tag).where(Tag.tenant_id == tenant.id, Tag.slug == slug))
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tag not found")
    if body.labels:
        tag.labels = {**(tag.labels or {}), **body.labels}
        tag.is_pinned = True
    if body.description is not None:
        tag.description = body.description
        tag.is_pinned = True
    if body.hidden is not None:
        tag.status = "hidden" if body.hidden else "active"
        tag.is_pinned = True
    return {"slug": tag.slug, "status": tag.status, "labels": tag.labels, "is_pinned": tag.is_pinned}


class TagMerge(BaseModel):
    into: str = Field(min_length=1, max_length=96)


@router.post("/tags/{slug}/merge")
async def merge_tag(
    slug: str,
    body: TagMerge,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fold one tag into another: its posts, its aliases and its old URL all follow."""
    source = await db.scalar(select(Tag).where(Tag.tenant_id == tenant.id, Tag.slug == slug))
    target = await db.scalar(select(Tag).where(Tag.tenant_id == tenant.id, Tag.slug == body.into))
    if source is None or target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tag not found")
    if source.id == target.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a tag cannot be merged into itself")

    post_ids = (await db.scalars(select(PostTag.post_id).where(PostTag.tag_id == source.id))).all()
    existing = set((await db.scalars(select(PostTag.post_id).where(PostTag.tag_id == target.id))).all())
    for post_id in post_ids:
        if post_id not in existing:
            db.add(
                PostTag(
                    post_id=post_id, tag_id=target.id, tenant_id=tenant.id, confidence=1.0, source="manual"
                )
            )
    await db.execute(PostTag.__table__.delete().where(PostTag.tag_id == source.id))

    aliases = (await db.scalars(select(TagAlias).where(TagAlias.tag_id == source.id))).all()
    target_norms = set(
        (await db.scalars(select(TagAlias.alias_norm).where(TagAlias.tag_id == target.id))).all()
    )
    for alias in [*aliases]:
        if alias.alias_norm not in target_norms:
            db.add(
                TagAlias(
                    tenant_id=tenant.id,
                    tag_id=target.id,
                    alias=alias.alias,
                    alias_norm=alias.alias_norm,
                    lang=alias.lang,
                    source="merge",
                )
            )
            target_norms.add(alias.alias_norm)
    if source.canonical_norm not in target_norms:
        db.add(
            TagAlias(
                tenant_id=tenant.id,
                tag_id=target.id,
                alias=source.canonical_name,
                alias_norm=source.canonical_norm,
                source="merge",
            )
        )

    source.status = "merged"
    source.merged_into_id = target.id
    source.is_pinned = True
    target.is_pinned = True
    target.post_count = len(existing | set(post_ids))
    await index_jobs.recompute_counts.defer_async(tenant_id=tenant.id)
    return {"merged": source.slug, "into": target.slug, "posts_moved": len(post_ids)}


@router.post("/tags/pending/{candidate_id}/promote")
async def promote_candidate(
    candidate_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    """Turn a recurring unmatched value into a real tag, with its observed spellings as aliases."""
    from kanalchi.ai.postprocess import ensure_tag
    from kanalchi.text.normalize import normalize

    candidate = await db.get(TagCandidate, candidate_id)
    if candidate is None or candidate.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")

    tag_id = await ensure_tag(db, tenant.id, candidate.dimension_id, candidate.name, source="manual")
    for alias in dict.fromkeys([candidate.name, *(candidate.surface_forms or [])]):
        alias_norm = normalize(alias)[:200]
        if not alias_norm:
            continue
        exists = await db.scalar(
            select(TagAlias.id).where(TagAlias.tag_id == tag_id, TagAlias.alias_norm == alias_norm)
        )
        if not exists:
            db.add(
                TagAlias(
                    tenant_id=tenant.id,
                    tag_id=tag_id,
                    alias=alias[:200],
                    alias_norm=alias_norm,
                    source="manual",
                )
            )
    candidate.status = "promoted"
    candidate.mapped_tag_id = tag_id
    tag = await db.get(Tag, tag_id)
    if tag is not None:
        tag.is_pinned = True
    await index_jobs.reassign.defer_async(tenant_id=tenant.id)
    return {"promoted": candidate.name, "tag_id": tag_id}


@router.post("/tags/pending/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: int, tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)
) -> dict:
    candidate = await db.get(TagCandidate, candidate_id)
    if candidate is None or candidate.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate not found")
    candidate.status = "rejected"
    return {"ok": True}


@router.post("/taxonomy/rebuild")
async def rebuild_taxonomy(tenant: Tenant = Depends(require_tenant)) -> dict:
    """Propose a new taxonomy version. It is not applied until someone reviews the diff."""
    job_run_id = await create_job_run(tenant.id, "taxonomy", {"trigger": "studio"})
    await index_jobs.build_taxonomy.configure(queueing_lock=f"taxonomy:{tenant.id}").defer_async(
        tenant_id=tenant.id, job_run_id=job_run_id, auto_apply=False
    )
    return {"job_run_id": job_run_id}


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
async def get_studio_settings(tenant: Tenant = Depends(require_tenant)) -> dict:
    settings = tenant.settings or {}
    return {
        "chat_enabled": settings.get("chat_enabled", True),
        "chat_persona": settings.get("chat_persona"),
        "voice_profile": settings.get("voice_profile"),
        "channel_profile": settings.get("channel_profile"),
        "bot_username": tenant.bot_username,
        "webhook_ready": bool(tenant.bot_token_enc and tenant.webhook_secret),
        "locales": tenant.locales,
    }
