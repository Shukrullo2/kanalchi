"""localised descriptions for dimensions and tags

The one-line description under an index group's title, and the one under a tag's
name, were single English strings written by the taxonomy model. They are read by
the same people who read the labels beside them, so they get the same shape as
`labels`: one entry per locale. Existing text is kept as the English entry.

Revision ID: a1c47f0b93e2
Revises: 79d88e2e21b6
Create Date: 2026-09-22 16:10:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a1c47f0b93e2"
down_revision = "79d88e2e21b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("dimensions", "tags"):
        op.add_column(
            table,
            sa.Column(
                "descriptions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.execute(
            f"""
            UPDATE {table}
            SET descriptions = jsonb_build_object('en', description)
            WHERE description IS NOT NULL AND btrim(description) <> ''
            """
        )
        op.drop_column(table, "description")


def downgrade() -> None:
    for table in ("dimensions", "tags"):
        op.add_column(table, sa.Column("description", sa.Text(), nullable=True))
        op.execute(f"UPDATE {table} SET description = descriptions ->> 'en'")
        op.drop_column(table, "descriptions")
