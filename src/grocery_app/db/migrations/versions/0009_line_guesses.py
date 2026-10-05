"""The photo reading's first guess per line: a plain name and a category.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "line_guesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("reading", sa.String(), nullable=True),
        sa.UniqueConstraint("receipt_id", "position"),
    )


def downgrade() -> None:
    op.drop_table("line_guesses")
