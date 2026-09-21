from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from kanalchi.core.models.base import Base, TenantMixin, TimestampMixin, pk


class ChatSession(TenantMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_tenant_user_last", "tenant_id", "user_id", "last_message_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    visitor_id: Mapped[str | None] = mapped_column(String(64))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(12), default="viewer")  # viewer|research
    title: Mapped[str | None] = mapped_column(String(200))
    locale: Mapped[str | None] = mapped_column(String(8))
    seed_post_id: Mapped[int | None] = mapped_column(BigInteger)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    summary_note: Mapped[str | None] = mapped_column(Text)  # compacted older turns
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(TenantMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session", "session_id", "id"),)

    id: Mapped[int] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)  # user|assistant
    content: Mapped[str] = mapped_column(Text, default="")
    content_blocks: Mapped[list[Any]] = mapped_column(
        JSONB, default=list
    )  # full API blocks incl. tool_use/tool_result
    citations: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    model: Mapped[str | None] = mapped_column(String(48))
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(24))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
