"""The word a product is searched for in the offers: `products.offer_word`, and
who gave it, `offer_word_by` (the prompt's version).

Found on live, 2026-10-23: a product's name is a poor search
(`Bio H-Alpenmilch 1,5% Fett, Laktosefrei` finds nothing), so a model gives
each regular product, once, the word a German flyer lists its kind under
(`offer_match.flyer_words`). Empty until then; the name is searched meanwhile.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("offer_word", sa.String(), nullable=True))
    op.add_column("products", sa.Column("offer_word_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "offer_word_by")
    op.drop_column("products", "offer_word")
