"""The tables behind purchases.json: receipts, lines, products, resolutions, listings,
and the shopper's line answers.

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MONEY = sa.Numeric(10, 2)


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_image", sa.String(), nullable=False, unique=True),
        sa.Column("transcribed_by", sa.String(), nullable=False),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("store_location", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("time", sa.String(length=8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("printed_total", MONEY, nullable=True),
        sa.Column("printed_savings", MONEY, nullable=True),
        sa.Column("tax_buckets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_gross", MONEY, nullable=True),
        sa.Column("gross", MONEY, nullable=True),
        sa.Column("discount", MONEY, nullable=True),
        sa.Column("net", MONEY, nullable=False),
        sa.Column("tax_class", sa.String(length=4), nullable=True),
        sa.Column("sold_by_weight", sa.Boolean(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(8, 3), nullable=True),
        sa.Column("unit_price", MONEY, nullable=True),
        sa.Column("unit_price_basis", sa.String(), nullable=True),
        sa.UniqueConstraint("receipt_id", "position"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("product_line", sa.String(), nullable=True),
        sa.Column("variant", sa.String(), nullable=True),
        sa.Column("size", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("is_organic", sa.Boolean(), nullable=True),
        sa.Column("is_own_brand", sa.Boolean(), nullable=True),
        sa.Column("eans", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("open_questions", postgresql.ARRAY(sa.String()), nullable=False,
                  server_default="{}"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "resolutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store", sa.String(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("line_type", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("product_ids", postgresql.ARRAY(sa.String()), nullable=False,
                  server_default="{}"),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("confirmed_by", sa.String(), nullable=True),
        sa.Column("confirmed_at", sa.Date(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.UniqueConstraint("store", "raw_name", "line_type"),
    )
    op.create_table(
        "store_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store", sa.String(), nullable=False),
        sa.Column("article_number", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("prices", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default="[]"),
        sa.UniqueConstraint("store", "article_number"),
    )
    op.create_table(
        "line_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("confirmed_by", sa.String(), nullable=True),
        sa.Column("confirmed_at", sa.Date(), nullable=True),
        sa.Column("basis", sa.String(), nullable=True),
        sa.UniqueConstraint("receipt_id", "position"),
    )


def downgrade() -> None:
    for table in ("line_resolutions", "store_listings", "resolutions",
                  "products", "receipt_lines", "receipts"):
        op.drop_table(table)
