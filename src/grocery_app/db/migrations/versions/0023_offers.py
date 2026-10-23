"""The shops' weekly offers, and the searches that found them.

The owner, 2026-10-23: show a user the offers for what they buy, refreshed
when each chain puts out its new ones. `offers` keeps every offer seen near
a postcode, with when it was first and last seen; `offer_searches` keeps
when each search word was last looked up there. Both are public data and
name no user.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("postcode", sa.String(5), nullable=False),
        sa.Column("chain", sa.String(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("record", JSONB(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_id", "postcode"),
    )
    op.create_index("ix_offers_postcode", "offers", ["postcode"])
    op.create_index("ix_offers_valid_to", "offers", ["valid_to"])
    op.create_table(
        "offer_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("postcode", sa.String(5), nullable=False),
        sa.Column("word", sa.String(), nullable=False),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("found", sa.Integer(), nullable=False),
        sa.UniqueConstraint("postcode", "word"),
    )


def downgrade() -> None:
    op.drop_table("offer_searches")
    op.drop_table("offers")
