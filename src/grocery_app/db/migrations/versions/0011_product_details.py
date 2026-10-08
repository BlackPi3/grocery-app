"""A product's range and variant become one list of details.

Parham, 2026-10-09: the range (`system`) and the variant were two fixed slots
the reader had to choose between for every printed word, and a word placed in
one slot one day and the other the next made two products of one. Neither
slot did a job of its own. Name, brand, category and size stay; everything
else the pack says is one list, any length, in the product's own words.

Existing rows: the range first, then the variant split at its commas.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("details", postgresql.ARRAY(sa.String()),
                                        nullable=False, server_default="{}"))
    op.execute("""
        UPDATE products SET details = ARRAY(
            SELECT trim(part) FROM unnest(
                array_remove(ARRAY[product_line], NULL)
                || coalesce(string_to_array(variant, ','), '{}')) AS part
            WHERE trim(part) <> '')
    """)
    op.drop_column("products", "product_line")
    op.drop_column("products", "variant")


def downgrade() -> None:
    op.add_column("products", sa.Column("product_line", sa.String(), nullable=True))
    op.add_column("products", sa.Column("variant", sa.String(), nullable=True))
    op.execute("UPDATE products SET variant = nullif(array_to_string(details, ', '), '')")
    op.drop_column("products", "details")
