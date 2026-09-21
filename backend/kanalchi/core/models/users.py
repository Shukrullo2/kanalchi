from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kanalchi.core.models.base import Base, TimestampMixin, pk


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = pk()
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    photo_url: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantMember(TimestampMixin, Base):
    __tablename__ = "tenant_members"

    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(12), default="owner")  # owner|editor
    verified_admin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dm_chat_id: Mapped[int | None] = mapped_column(BigInteger)  # set once the member /start-s the tenant bot


class PlatformAdmin(TimestampMixin, Base):
    __tablename__ = "platform_admins"

    tg_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    note: Mapped[str | None] = mapped_column(String(255))
