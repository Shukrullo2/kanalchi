"""self-serve sign-up: tenant owner, plans and subscriptions

Revision ID: c7d2e9a4b1f3
Revises: 5b1f0c7e2a9d
Create Date: 2026-09-24 12:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c7d2e9a4b1f3"
down_revision = "5b1f0c7e2a9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("signed_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("owner_user_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_tenants_owner_user_id_users", "tenants", "users", ["owner_user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_tenants_owner_user_id", "tenants", ["owner_user_id"])
    op.add_column("tenants", sa.Column("source", sa.String(16), nullable=False, server_default="admin"))
    op.add_column("tenants", sa.Column("plan", sa.String(16), nullable=True))
    op.add_column(
        "tenants", sa.Column("subscription_status", sa.String(16), nullable=False, server_default="none")
    )
    op.add_column("tenants", sa.Column("subscription_paid_until", sa.Date(), nullable=True))
    op.add_column("tenants", sa.Column("onboarding_quote", postgresql.JSONB(), nullable=True))
    op.add_column("tenants", sa.Column("onboarding_paid_at", sa.DateTime(timezone=True), nullable=True))
    # Channels connected by hand before plans existed keep everything they had: the full studio
    # and live updates, i.e. premium, with nothing owed.
    op.execute("UPDATE tenants SET plan = 'premium', subscription_status = 'active' WHERE plan IS NULL")


def downgrade() -> None:
    op.drop_column("tenants", "onboarding_paid_at")
    op.drop_column("tenants", "onboarding_quote")
    op.drop_column("tenants", "subscription_paid_until")
    op.drop_column("tenants", "subscription_status")
    op.drop_column("tenants", "plan")
    op.drop_column("tenants", "source")
    op.drop_index("ix_tenants_owner_user_id", table_name="tenants")
    op.drop_constraint("fk_tenants_owner_user_id_users", "tenants", type_="foreignkey")
    op.drop_column("tenants", "owner_user_id")
    op.drop_column("users", "signed_up_at")
