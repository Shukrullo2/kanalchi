from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kanalchi.core.models.base import Base, TenantMixin, TimestampMixin, pk

EMBED_DIM = 1024


class Post(TenantMixin, TimestampMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_message_id", name="uq_posts_channel_msg"),
        Index("ix_posts_tenant_date", "tenant_id", "date", postgresql_ops={"date": "DESC"}),
        Index("ix_posts_tenant_views", "tenant_id", "views", postgresql_ops={"views": "DESC"}),
        Index(
            "ix_posts_tenant_engagement",
            "tenant_id",
            "engagement_score",
            postgresql_ops={"engagement_score": "DESC"},
        ),
        Index("ix_posts_tenant_grouped", "tenant_id", "grouped_id"),
        Index("ix_posts_tenant_index_status", "tenant_id", "index_status"),
        Index("ix_posts_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_posts_text_norm_trgm",
            "text_norm",
            postgresql_using="gin",
            postgresql_ops={"text_norm": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = pk()
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    tg_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    grouped_id: Mapped[int | None] = mapped_column(BigInteger)
    is_album_root: Mapped[bool] = mapped_column(Boolean, default=True)
    text: Mapped[str] = mapped_column(Text, default="")
    text_norm: Mapped[str] = mapped_column(Text, default="")
    entities: Mapped[list[Any]] = mapped_column(
        JSONB, default=list
    )  # Telegram MessageEntity[] (UTF-16 offsets)
    html: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int] = mapped_column(Integer, default=0)
    forwards: Mapped[int] = mapped_column(Integer, default=0)
    reactions: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # [{emoji|custom_emoji_id, count}]
    reactions_total: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    reply_to_tg_message_id: Mapped[int | None] = mapped_column(BigInteger)
    forward_from: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    media_kind: Mapped[str] = mapped_column(String(16), default="none")
    # none|photo|video|document|audio|voice|sticker|animation|poll|album|other
    poll: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str | None] = mapped_column(String(12))
    title: Mapped[str | None] = mapped_column(String(160))
    summary: Mapped[str | None] = mapped_column(String(400))
    index_status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|embedded|extracted|tagged|skipped
    extraction_version: Mapped[int | None] = mapped_column(Integer)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(text, '') || ' ' || coalesce(text_norm, ''))", persisted=True
        ),
    )

    media: Mapped[list[Media]] = relationship(
        back_populates="post", order_by="Media.position", cascade="all, delete-orphan"
    )
    links: Mapped[list[PostLink]] = relationship(back_populates="post", cascade="all, delete-orphan")


class Media(TenantMixin, TimestampMixin, Base):
    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("post_id", "tg_file_unique_id", name="uq_media_post_file"),
        Index("ix_media_tenant_post", "tenant_id", "post_id"),
        Index("ix_media_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = pk()
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    tg_file_unique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tg_file_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict
    )  # what Telethon needs to re-download
    kind: Mapped[str] = mapped_column(String(16), default="photo")
    mime: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    file_name: Mapped[str | None] = mapped_column(String(255))
    object_key: Mapped[str | None] = mapped_column(String(512))
    thumb_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|stored|too_large|protected|failed
    external_url: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    post: Mapped[Post] = relationship(back_populates="media")


class PostLink(TenantMixin, TimestampMixin, Base):
    __tablename__ = "post_links"
    __table_args__ = (
        Index("ix_post_links_tenant_domain", "tenant_id", "domain"),
        Index("ix_post_links_post", "post_id"),
    )

    id: Mapped[int] = pk()
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_norm: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(253), default="")
    kind: Mapped[str | None] = mapped_column(
        String(16)
    )  # news|social|official|video|shop|telegram|document|other
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(500))
    unfurled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)

    post: Mapped[Post] = relationship(back_populates="links")


class PostChunk(TenantMixin, Base):
    __tablename__ = "post_chunks"
    __table_args__ = (
        UniqueConstraint("post_id", "position", name="uq_post_chunks_post_pos"),
        Index("ix_post_chunks_tenant_post", "tenant_id", "post_id"),
        Index(
            "ix_post_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 128},
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
    )

    id: Mapped[int] = pk()
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, default=0)  # -1 = synthetic Latin summary chunk
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Any | None] = mapped_column(HALFVEC(EMBED_DIM))
    embed_model: Mapped[str | None] = mapped_column(String(32))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
