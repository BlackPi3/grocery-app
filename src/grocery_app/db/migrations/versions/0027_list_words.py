"""The word a shopping list calls a flyer word's kind: `list_words`.

The owner, 2026-10-25: a list line is the word a person writes on a paper
list, so Romatomaten and Rispentomaten are one line, "Tomaten". The flyer
word (`products.offer_word`) stays what offers are searched by.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_words",
        sa.Column("word", sa.String(), primary_key=True),
        sa.Column("list_word", sa.String(), nullable=False),
        sa.Column("given_by", sa.String(), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )


def downgrade() -> None:
    op.drop_table("list_words")
