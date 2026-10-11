"""Accounts: people other than the owner, with their own receipts.

Parham, 2026-10-11: a UX designer will use the app with her own receipts,
from shops he does not use; the catalog and the memory are shared, her
answers count with less weight than his. The owner has no row: everything
with no user is the owner's, so no existing row changes.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    for table in ("receipts", "jobs"):
        op.add_column(table, sa.Column("user_id", sa.Integer(),
                                       sa.ForeignKey("users.id", ondelete="CASCADE"),
                                       nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    op.add_column("line_resolutions", sa.Column("disagrees_with", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("line_resolutions", "disagrees_with")
    for table in ("jobs", "receipts"):
        op.drop_index(f"ix_{table}_user_id", table)
        op.drop_column(table, "user_id")
    op.drop_table("users")
