"""Studio membership: who may enter a channel's studio, and how they got in.

A member either proved through Telegram that they administer the channel, or was invited
by an admin or the owner. The invited path exists so a channel without a bot of its own
can still have a blogger, and so an owner can bring in an editor who is not a channel admin.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.core.models import TenantMember, User

ROLES = {"owner", "editor"}


def member_out(member: TenantMember, user: User) -> dict[str, Any]:
    return {
        "tg_user_id": user.tg_user_id,
        "name": " ".join(x for x in [user.first_name, user.last_name] if x)
        or user.username
        or str(user.tg_user_id),
        "username": user.username,
        "role": member.role,
        "invited": member.invited,
        "verified_admin_at": member.verified_admin_at,
        "notifications_linked": member.dm_chat_id is not None,
        "last_login_at": user.last_login_at,
    }


async def list_members(db: AsyncSession, tenant_id: int) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(TenantMember, User)
            .join(User, User.id == TenantMember.user_id)
            .where(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.created_at)
        )
    ).all()
    return [member_out(m, u) for m, u in rows]


async def invite_member(
    db: AsyncSession, tenant_id: int, tg_user_id: int, role: str, name: str | None = None
) -> dict[str, Any]:
    """Add (or re-role) a member by Telegram id. The user row is created if they have never signed in."""
    if role not in ROLES:
        raise ValueError("role must be owner or editor")
    stmt = insert(User).values(tg_user_id=tg_user_id, first_name=name or None)
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.tg_user_id],
        # A name given at invite time never overwrites what Telegram told us at sign-in.
        set_={"first_name": User.__table__.c.first_name},
    ).returning(User.id)
    user_id = await db.scalar(stmt)
    member = await db.scalar(
        select(TenantMember).where(TenantMember.tenant_id == tenant_id, TenantMember.user_id == user_id)
    )
    if member is None:
        member = TenantMember(tenant_id=tenant_id, user_id=user_id, role=role, invited=True)
        db.add(member)
    else:
        member.role = role
        member.invited = True
    member.updated_at = datetime.now(UTC)
    await db.flush()
    user = await db.get(User, user_id)
    return member_out(member, user)


async def remove_member(db: AsyncSession, tenant_id: int, tg_user_id: int) -> bool:
    row = await db.scalar(
        select(TenantMember)
        .join(User, User.id == TenantMember.user_id)
        .where(TenantMember.tenant_id == tenant_id, User.tg_user_id == tg_user_id)
    )
    if row is None:
        return False
    await db.delete(row)
    return True
