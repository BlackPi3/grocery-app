"""Log a machine's answer the shopper overruled.

From catalog-growth step 5 on, answers are remembered and apply to the next
receipt at once. A machine answer the shopper corrects is replaced, and this
table keeps the mistake, so the rate of wrong automatic answers is known.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("machine_how", sa.String(), nullable=False),
        sa.Column("machine_product_id", sa.String(), nullable=False),
        sa.Column("shopper_product_id", sa.String(), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("corrections")
