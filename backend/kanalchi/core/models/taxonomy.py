from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kanalchi.core.models.base import Base, TenantMixin, TimestampMixin, pk
from kanalchi.core.models.content import EMBED_DIM


class LlmBatch(TenantMixin, TimestampMixin, Base):
    __tablename__ = "llm_batches"

    id: Mapped[int] = pk()
    anthropic_batch_id: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16), default="extract")  # extract|map_tags
    model: Mapped[str] = mapped_column(String(48), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="submitted"
    )  # submitted|in_progress|ended|canceled|expired|failed
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    expired: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)


class Extraction(TenantMixin, TimestampMixin, Base):
    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint("post_id", "extractor_version", name="uq_extractions_post_version"),
        Index("ix_extractions_batch", "llm_batch_id"),
        Index("ix_extractions_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = pk()
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    extractor_version: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[str] = mapped_column(String(48), default="")
    prompt_version: Mapped[str] = mapped_column(String(16), default="")
    llm_batch_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("llm_batches.id", ondelete="SET NULL")
    )
    custom_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), default="queued"
    )  # queued|submitted|succeeded|errored|refused|invalid
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Dimension(TenantMixin, TimestampMixin, Base):
    __tablename__ = "dimensions"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_dimensions_tenant_key"),)

    id: Mapped[int] = pk()
    key: Mapped[str] = mapped_column(String(48), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="open")  # open|fixed|programmatic
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {uz, ru, en}
    description: Mapped[str | None] = mapped_column(Text)
    extraction_hint: Mapped[str | None] = mapped_column(Text)
    is_universal: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class TaxonomyVersion(TenantMixin, TimestampMixin, Base):
    __tablename__ = "taxonomy_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "version_no", name="uq_taxonomy_versions_tenant_no"),)

    id: Mapped[int] = pk()
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(16), default="building"
    )  # building|proposed|applied|failed|archived
    model: Mapped[str] = mapped_column(String(48), default="")
    candidate_stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Tag(TenantMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_tags_tenant_slug"),
        UniqueConstraint("tenant_id", "dimension_id", "canonical_norm", name="uq_tags_tenant_dim_norm"),
        Index("ix_tags_tenant_dim_count", "tenant_id", "dimension_id", "post_count"),
    )

    id: Mapped[int] = pk()
    dimension_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dimensions.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_norm: Mapped[str] = mapped_column(String(200), nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tags.id", ondelete="SET NULL"))
    merged_into_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tags.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|hidden|merged
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="taxonomy")  # taxonomy|manual|programmatic
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen_version: Mapped[int | None] = mapped_column(Integer)
    last_seen_version: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[Any | None] = mapped_column(HALFVEC(EMBED_DIM))

    dimension: Mapped[Dimension] = relationship()
    aliases: Mapped[list[TagAlias]] = relationship(back_populates="tag", cascade="all, delete-orphan")


class TagAlias(TenantMixin, Base):
    __tablename__ = "tag_aliases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tag_id", "alias_norm", name="uq_tag_aliases_tag_norm"),
        Index("ix_tag_aliases_tenant_norm", "tenant_id", "alias_norm"),
    )

    id: Mapped[int] = pk()
    tag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    alias_norm: Mapped[str] = mapped_column(String(200), nullable=False)
    lang: Mapped[str | None] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(12), default="llm")  # llm|manual|merge|surface

    tag: Mapped[Tag] = relationship(back_populates="aliases")


class PostTag(Base):
    __tablename__ = "post_tags"
    __table_args__ = (Index("ix_post_tags_tenant_tag_post", "tenant_id", "tag_id", "post_id"),)

    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(
        String(16), default="alias"
    )  # extractor|alias|embedding|llm_map|manual|programmatic
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class TagCandidate(TenantMixin, TimestampMixin, Base):
    """Pending tags: extracted candidates that did not map onto the active taxonomy."""

    __tablename__ = "tag_candidates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dimension_id", "name_norm", name="uq_tag_candidates_tenant_dim_norm"),
    )

    id: Mapped[int] = pk()
    dimension_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dimensions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_norm: Mapped[str] = mapped_column(String(200), nullable=False)
    lang: Mapped[str | None] = mapped_column(String(8))
    count: Mapped[int] = mapped_column(Integer, default=1)
    sample_post_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    surface_forms: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    mean_engagement: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|mapped|promoted|rejected
    mapped_tag_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tags.id", ondelete="SET NULL"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Thread(TenantMixin, TimestampMixin, Base):
    __tablename__ = "threads"

    id: Mapped[int] = pk()
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    title: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    first_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="active")
    citations: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)


class ThreadPost(Base):
    __tablename__ = "thread_posts"

    thread_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )


class EntitySummary(TenantMixin, TimestampMixin, Base):
    __tablename__ = "entity_summaries"

    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {uz, ru, en}
    citations: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean, default=True)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
