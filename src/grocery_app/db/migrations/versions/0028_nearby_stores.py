"""Where the shops on receipts are, and the supermarkets around them:
`shop_places`, `nearby_stores`.

The owner, 2026-10-25: the list's cost is compared at the supermarkets near
the shops a person uses, not only at those they go to.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False, unique=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("postcode", sa.String(5), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("located_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stores_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "nearby_stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("place_id", sa.Integer(),
                  sa.ForeignKey("shop_places.id", ondelete="CASCADE"), nullable=False),
        sa.Column("osm_id", sa.String(), nullable=False),
        sa.Column("chain", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.UniqueConstraint("place_id", "osm_id"),
    )
    op.create_index("ix_nearby_stores_place_id", "nearby_stores", ["place_id"])


def downgrade() -> None:
    op.drop_table("nearby_stores")
    op.drop_table("shop_places")
