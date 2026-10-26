"""The kinds close to groceries a person counts as well: `counted_kinds`.

The owner, 2026-10-26: only groceries count by default; a person may add
things close to them that a market sells too (alcohol, supplements,
household, ...: `categories.CLOSE_KINDS`). One row per kind switched on.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counted_kinds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
    )
    op.create_index("ix_counted_kinds_user_id", "counted_kinds", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_counted_kinds_user_id", table_name="counted_kinds")
    op.drop_table("counted_kinds")
