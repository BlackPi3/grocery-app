"""Spot checks: lines the app placed on its own, put to the shopper.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("app_product_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("receipt_id", "position"),
    )


def downgrade() -> None:
    op.drop_table("checks")
