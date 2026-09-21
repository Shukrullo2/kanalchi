from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kanalchi.core.models.base import Base, TimestampMixin, pk


class TelegramAccount(TimestampMixin, Base):
    """A real Telegram user account whose MTProto session reads channel history."""

    __tablename__ = "telegram_accounts"

    id: Mapped[int] = pk()
    phone: Mapped[str] = mapped_column(String(32), unique=True)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(String(128))
    session_enc: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted StringSession
    status: Mapped[str] = mapped_column(String(24), default="pending_code")
    # pending_code | pending_password | active | flood_wait | dead | disabled
    health: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    flood_wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channels: Mapped[list[Channel]] = relationship(back_populates="account")


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[int] = pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="onboarding", index=True)
    # onboarding | backfilling | indexing | active | paused | error | archived
    title: Mapped[str] = mapped_column(String(255), default="")
    primary_lang: Mapped[str] = mapped_column(String(8), default="uz")
    locales: Mapped[list[str]] = mapped_column(ARRAY(String(8)), default=lambda: ["uz", "ru", "en"])
    bot_token_enc: Mapped[str | None] = mapped_column(Text)
    bot_id: Mapped[int | None] = mapped_column(BigInteger)
    bot_username: Mapped[str | None] = mapped_column(String(64))
    webhook_secret: Mapped[str | None] = mapped_column(String(64))
    domain_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_taxonomy_version_id: Mapped[int | None] = mapped_column(BigInteger)
    daily_chat_budget_usd: Mapped[float] = mapped_column(Numeric(8, 2), default=5)
    daily_studio_budget_usd: Mapped[float] = mapped_column(Numeric(8, 2), default=20)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # settings keys: voice_profile, channel_profile, chat_persona, media_policy ('store'|'link_only'), theme, features

    channel: Mapped[Channel | None] = relationship(back_populates="tenant", uselist=False)


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (Index("ix_channels_tenant", "tenant_id"),)

    id: Mapped[int] = pk()
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True
    )
    telegram_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("telegram_accounts.id", ondelete="SET NULL")
    )
    tg_channel_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    access_hash: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), default="")
    about: Mapped[str | None] = mapped_column(Text)
    photo_key: Mapped[str | None] = mapped_column(String(512))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    noforwards: Mapped[bool] = mapped_column(Boolean, default=False)
    participants_count: Mapped[int | None] = mapped_column(Integer)
    backfill_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|error
    backfill_checkpoint: Mapped[int] = mapped_column(BigInteger, default=0)
    backfill_total_estimate: Mapped[int | None] = mapped_column(Integer)
    last_live_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_resync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship(back_populates="channel")
    account: Mapped[TelegramAccount | None] = relationship(back_populates="channels")
