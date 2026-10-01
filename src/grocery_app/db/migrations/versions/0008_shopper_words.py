"""The shopper's own words, kept beside a described answer.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_resolutions", sa.Column("shopper_words", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("line_resolutions", "shopper_words")
