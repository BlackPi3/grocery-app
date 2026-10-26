"""When the shopper skipped a question or a spot check: `skipped_at`.

The owner, 2026-10-26: a person may not want to answer, or not remember
(an old receipt). "Skip" is not an answer: the line keeps the app's guess,
and the card goes to the back, to come again after the others.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("questions", "checks"):
        op.add_column(table, sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in ("checks", "questions"):
        op.drop_column(table, "skipped_at")
