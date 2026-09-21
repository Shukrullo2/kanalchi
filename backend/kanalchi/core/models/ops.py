from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kanalchi.core.models.base import Base, TimestampMixin, pk


class JobRun(TimestampMixin, Base):
    """Admin-facing job record (procrastinate keeps its own queue tables)."""

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_tenant_type_created", "tenant_id", "type", "created_at"),
        Index("ix_job_runs_status", "status"),
    )

    id: Mapped[int] = pk()
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default="queued"
    )  # queued|running|succeeded|failed|canceled
    procrastinate_job_id: Mapped[int | None] = mapped_column(BigInteger)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # {stage, done, total, checkpoint, message}
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (UniqueConstraint("tenant_id", "day", "model", "purpose", name="uq_usage_ledger_key"),)

    id: Mapped[int] = pk()
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(16), default="anthropic")
    model: Mapped[str] = mapped_column(String(48), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = pk()
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"))
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
