from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kanalchi.core.models.base import Base, TenantMixin, TimestampMixin, pk


class Idea(TenantMixin, TimestampMixin, Base):
    __tablename__ = "ideas"
    __table_args__ = (Index("ix_ideas_tenant_status_pos", "tenant_id", "status", "position"),)

    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(16), default="inbox"
    )  # inbox|researching|drafting|scheduled|published|dropped
    position: Mapped[int] = mapped_column(Integer, default=0)
    tag_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    related_post_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    source_chat_message_id: Mapped[int | None] = mapped_column(BigInteger)


class Draft(TenantMixin, TimestampMixin, Base):
    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_tenant_status_sched", "tenant_id", "status", "scheduled_at"),)

    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    idea_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ideas.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), default="")
    html: Mapped[str] = mapped_column(Text, default="")  # Telegram HTML subset
    media: Mapped[list[Any]] = mapped_column(
        JSONB, default=list
    )  # [{upload_id, object_key, kind, mime, w, h}]
    disable_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(
        String(16), default="draft"
    )  # draft|scheduled|publishing|published|failed|canceled
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_job_id: Mapped[int | None] = mapped_column(BigInteger)
    published_tg_message_id: Mapped[int | None] = mapped_column(BigInteger)
    published_post_id: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_error: Mapped[str | None] = mapped_column(Text)
    suggested_tags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_prompt: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Upload(TenantMixin, TimestampMixin, Base):
    __tablename__ = "uploads"

    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    thumb_key: Mapped[str | None] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), default="photo")
    status: Mapped[str] = mapped_column(String(12), default="ready")
