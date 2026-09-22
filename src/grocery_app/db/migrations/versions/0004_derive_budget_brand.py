"""Stop storing is_own_brand on a product; it is derived per purchase line.

The column and the field were renamed to `is_budget_brand` in the same change:
the question is whether a brand is the shop's cheaper line, not who owns it.
The column is dropped rather than renamed, so only the old name appears here.

Whether a brand is the shop's own label is a fact about a brand *and* a shop,
not about a product. Frozen onto the product at mint time it could only ever
answer for the shop the product was first seen in, and it drifted: the same
brand carried different values on different rows, and 99 of 181 products
carried no value at all because two of the four writers never asked.

The normalizer now answers the question as each line is read, from the line's
store and the product's brand, so extending the brand tables reaches every row
ever written. Nothing downstream loses the field: purchases.json still carries
`is_budget_brand` on every line, which is where it belonged all along.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("products", "is_own_brand")


def downgrade() -> None:
    # The column comes back empty. The values it used to hold were a frozen
    # copy of a derived answer, so restoring them would mean re-freezing a
    # guess; anything that wants the fact should ask `budget_brand_status`.
    op.add_column("products", sa.Column("is_own_brand", sa.Boolean(), nullable=True))
