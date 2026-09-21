"""Public viewer API on tenant hosts (Phase 1 adds posts; Phase 2 adds tags/search)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import get_db, require_tenant
from kanalchi.core.models import Channel, Post, Tenant

router = APIRouter(prefix="/api", tags=["viewer"])


@router.get("/tenant")
async def tenant_info(tenant: Tenant = Depends(require_tenant), db: AsyncSession = Depends(get_db)) -> dict:
    channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
    post_count = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
    )
    return {
        "id": tenant.id,
        "slug": tenant.slug,
        "domain": tenant.domain,
        "status": tenant.status,
        "title": tenant.title or (channel.title if channel else ""),
        "about": channel.about if channel else None,
        "username": channel.username if channel else None,
        "photo_key": channel.photo_key if channel else None,
        "primary_lang": tenant.primary_lang,
        "locales": tenant.locales,
        "bot_username": tenant.bot_username,
        "post_count": post_count or 0,
        "theme": (tenant.settings or {}).get("theme", {}),
    }
