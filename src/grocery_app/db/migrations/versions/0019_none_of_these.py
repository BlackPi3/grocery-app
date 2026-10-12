"""A line answer may say "none of these": no product.

Parham, 2026-10-12: questions and spot checks become yes/no cards with
pictures, and no typing. A No on every card leaves the line not placed, and
says so, so it is not asked again; a No on a spot check also says which
product was wrong (`rejected`). A machine's mistake overruled that way is
still counted in `corrections`, with no product of the shopper's.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("line_resolutions", "product_id", nullable=True)
    op.add_column("line_resolutions", sa.Column("rejected", sa.String(), nullable=True))
    op.alter_column("corrections", "shopper_product_id", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM corrections WHERE shopper_product_id IS NULL")
    op.alter_column("corrections", "shopper_product_id", nullable=False)
    op.drop_column("line_resolutions", "rejected")
    op.execute("DELETE FROM line_resolutions WHERE product_id IS NULL")
    op.alter_column("line_resolutions", "product_id", nullable=False)
