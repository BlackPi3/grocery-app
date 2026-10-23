"""Which offers are for which products: `offers.words`, `offer_verdicts`.

The owner, 2026-10-23, offers step 1b: an offer is matched to a person's
regular product when the product's search word found it and a model judged
it that product or the same kind (`offer_match`). The words say which
searches found an offer; a verdict is about a product and an offer, never a
person.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("words", ARRAY(sa.String()), nullable=False,
                                      server_default="{}"))
    op.create_table(
        "offer_verdicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.String(),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("judged_by", sa.String(), nullable=False),
        sa.Column("judged_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.UniqueConstraint("product_id", "source", "source_id"),
    )


def downgrade() -> None:
    op.drop_table("offer_verdicts")
    op.drop_column("offers", "words")
