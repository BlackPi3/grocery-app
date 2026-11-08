"""What each chain sells: `chain_products` and their dated `chain_prices`.

The owner, 2026-11-08 (`docs/designs/products-and-resolutions.md`): searching a
chain's JSON file means the server holds all of it in memory. A new table
rather than wider `store_listings`, whose rows are all read in several places
and need a product of ours.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chain_products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chain", sa.String, nullable=False),
        sa.Column("article_number", sa.String, nullable=False),
        sa.Column("ean", sa.String),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("brand", sa.String),
        sa.Column("pack_size", sa.String),
        sa.Column("category", sa.String),
        sa.Column("url", sa.String),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column("first_seen", sa.Date, nullable=False),
        sa.Column("last_seen", sa.Date, nullable=False),
        sa.Column("gone_since", sa.Date),
        sa.UniqueConstraint("chain", "article_number"),
    )
    op.create_table(
        "chain_prices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chain_product_id", sa.Integer,
                  sa.ForeignKey("chain_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seen_on", sa.Date, nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.UniqueConstraint("chain_product_id", "seen_on"),
    )


def downgrade() -> None:
    op.drop_table("chain_prices")
    op.drop_table("chain_products")
