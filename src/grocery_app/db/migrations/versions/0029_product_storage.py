"""Where a product is kept and how long it keeps: `products.storage`,
`products.keeps_days` (`grocery_app.storage`).

The owner, 2026-10-25: a trip buys ahead what keeps, as far as room at home
allows; both facts are a product's, given by a model.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("storage", sa.String(), nullable=True))
    op.add_column("products", sa.Column("keeps_days", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("storage_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "storage_by")
    op.drop_column("products", "keeps_days")
    op.drop_column("products", "storage")
