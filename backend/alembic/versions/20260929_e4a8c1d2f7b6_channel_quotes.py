"""channel quotes: pricing a channel no longer creates a tenant

Revision ID: e4a8c1d2f7b6
Revises: c7d2e9a4b1f3
Create Date: 2026-09-29 12:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e4a8c1d2f7b6"
down_revision = "c7d2e9a4b1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_quotes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("participants_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("quote", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("times_asked", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Channels registered through the old signed-in flow held their slug and domain from the
    # moment they were typed in. Those never imported are dropped, so the names are free again;
    # anything imported or created by the admin (the-bakiroo) stays.
    op.execute(
        """
        DELETE FROM tenants
        WHERE source = 'self' AND status = 'onboarding'
          AND NOT EXISTS (
            SELECT 1 FROM posts p JOIN channels c ON c.id = p.channel_id WHERE c.tenant_id = tenants.id
          )
        """
    )


def downgrade() -> None:
    op.drop_table("channel_quotes")
