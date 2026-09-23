"""invited members

Revision ID: 5b1f0c7e2a9d
Revises: a1c47f0b93e2
Create Date: 2026-09-23 09:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "5b1f0c7e2a9d"
down_revision = "a1c47f0b93e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_members",
        sa.Column("invited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tenant_members", "invited")
