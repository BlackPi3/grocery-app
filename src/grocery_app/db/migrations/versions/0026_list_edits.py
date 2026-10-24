"""A person's changes to their shopping list: `list_edits`.

The owner, 2026-10-23, the shopping list step 2: the person removes what they
don't need now and adds what they do. A removal is a snooze that doubles each
time without a buy (2026-10-24); the list is worked out from these rows and
the receipts, so a row is kept as it happened.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_edits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("edit", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_list_edits_user_id", "list_edits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_list_edits_user_id", table_name="list_edits")
    op.drop_table("list_edits")
