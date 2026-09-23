"""Chat endpoints: sessions and the SSE turn stream."""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from kanalchi.ai.chat.agent import budget_note, run_turn
from kanalchi.api.auth import SessionData
from kanalchi.api.deps import current_user, enforce_same_origin, get_db, require_tenant
from kanalchi.core.limits import check_chat_rate, check_platform_cap, ip_hash
from kanalchi.core.logging import get_logger
from kanalchi.core.models import ChatMessage, ChatSession, Post, Tenant

log = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

VISITOR_COOKIE = "kv"
MAX_MESSAGE_CHARS = 2000


def _visitor_id(request: Request, response: Response | None = None) -> str:
    """Anonymous, per-browser id used for the daily quota. Not an identity, just a bucket."""
    existing = request.cookies.get(VISITOR_COOKIE)
    if existing:
        return existing
    fresh = secrets.token_urlsafe(16)
    if response is not None:
        response.set_cookie(VISITOR_COOKIE, fresh, max_age=31536000, httponly=True, samesite="lax", path="/")
    return fresh


class SessionCreate(BaseModel):
    kind: str = Field(default="viewer", pattern="^(viewer|research)$")
    seed_post_id: int | None = None
    locale: str | None = None


@router.post("/sessions", status_code=201, dependencies=[Depends(enforce_same_origin)])
async def create_session(
    body: SessionCreate,
    request: Request,
    response: Response,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData | None = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.kind == "research" and (user is None or user.tenant_id != tenant.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "research chat is for channel members")
    if tenant.status == "paused":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "this channel is paused")
    if not (tenant.settings or {}).get("chat_enabled", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "chat is disabled for this channel")

    visitor = _visitor_id(request, response)
    session = ChatSession(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.user_id if user else None,
        visitor_id=visitor,
        ip_hash=ip_hash(request.client.host if request.client else None),
        kind=body.kind,
        locale=body.locale or tenant.primary_lang,
        seed_post_id=body.seed_post_id,
    )
    db.add(session)
    await db.flush()
    return {"session_id": str(session.id), "kind": session.kind}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


@router.post("/sessions/{session_id}/messages", dependencies=[Depends(enforce_same_origin)])
async def send_message(
    session_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    tenant: Tenant = Depends(require_tenant),
    user: SessionData | None = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    session = await db.get(ChatSession, session_id)
    if session is None or session.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat session not found")
    if session.kind == "research" and (user is None or user.tenant_id != tenant.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "research chat is for channel members")

    if not await check_platform_cap():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "the platform is over its daily assistant budget"
        )

    if session.kind == "viewer":
        limit = await check_chat_rate(
            tenant.id,
            ip=request.client.host if request.client else None,
            visitor_id=request.cookies.get(VISITOR_COOKIE),
        )
        if not limit.allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "too many questions in a short time, try again in a few minutes",
                headers={"Retry-After": str(limit.retry_after_s or 600)},
            )

    note, blocked = await budget_note(tenant, session.kind)
    if blocked:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "this channel's assistant is resting until tomorrow"
        )

    seed = None
    if session.seed_post_id and (session.message_count or 0) == 0:
        seed = session.seed_post_id

    # Detach from the request-scoped session: the generator outlives this handler.
    tenant_copy = await db.get(Tenant, tenant.id)
    db.expunge(tenant_copy)
    text = body.text if seed is None else f"(about post {seed})\n{body.text}"

    async def stream():  # noqa: ANN202
        async for event in run_turn(
            tenant=tenant_copy,
            session_id=session_id,
            user_text=text,
            kind=session.kind,
            locale=session.locale or tenant_copy.primary_lang,
            budget_note=note,
        ):
            yield {"event": event.type, "data": event.sse().split("data: ", 1)[1].strip()}

    return EventSourceResponse(stream(), ping=15000)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(ChatSession, session_id)
    if session is None or session.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat session not found")
    rows = (
        await db.scalars(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        )
    ).all()
    return {
        "session_id": str(session.id),
        "kind": session.kind,
        "title": session.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "citations": m.citations or [],
                "created_at": m.created_at,
            }
            for m in rows
            if m.content
        ],
    }


# Opening prompts, phrased in each interface language. The channel's own top tags are slotted in,
# so the first question is always about something this channel actually covers.
SUGGESTION_TEMPLATES: dict[str, dict[str, str]] = {
    "uz": {
        "about_tag": "Kanal {name} haqida nima yozgan?",
        "recent": "Shu oyning asosiy xabarlari nima edi?",
        "general": "Bu kanal nima haqida yozadi?",
    },
    "ru": {
        "about_tag": "Что канал писал про {name}?",
        "recent": "Какие главные новости были в этом месяце?",
        "general": "О чём этот канал?",
    },
    "en": {
        "about_tag": "What has this channel said about {name}?",
        "recent": "What were the main stories this month?",
        "general": "What does this channel write about?",
    },
}


@router.get("/suggestions")
async def suggestions(
    request: Request,
    tenant: Tenant = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Opening prompts built from the channel itself, so the first question is never a blank page."""
    from sqlalchemy import func

    from kanalchi.core.models import Dimension, Tag

    locale = (request.cookies.get("locale") or tenant.primary_lang or "en").split("-")[0]
    phrases = SUGGESTION_TEMPLATES.get(locale, SUGGESTION_TEMPLATES["en"])

    top = (
        await db.execute(
            select(Tag.canonical_name, Tag.labels)
            .join(Dimension, Dimension.id == Tag.dimension_id)
            .where(
                Tag.tenant_id == tenant.id,
                Tag.status == "active",
                Dimension.key.in_(["themes", "people", "gov_orgs"]),
            )
            .order_by(Tag.post_count.desc())
            .limit(4)
        )
    ).all()
    recent = await db.scalar(
        select(func.max(Post.date)).where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False))
    )

    out = [phrases["about_tag"].format(name=(labels or {}).get(locale) or name) for name, labels in top[:2]]
    if recent:
        out.append(phrases["recent"])
    out.append(phrases["general"])
    return {"suggestions": out[:4], "enabled": bool((tenant.settings or {}).get("chat_enabled", True))}
