"""A photo that is not a shop receipt is turned away.

Parham, 2026-10-08: a restaurant bill was read like a shop receipt and
entered the history. The reader now says where the paper is from; a job for
anything but a shop stores no receipt and keeps the reader's answer here.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("turned_away", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "turned_away")
