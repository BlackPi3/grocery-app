"""When an upload was handed to the developer to look at.

Parham, 2026-10-11: new kinds of upload (another person's receipts, a PDF
export, a failure) should reach development by themselves, "a trigger so
when something new is seen we analyze it here in the dev".

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("dev_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "dev_seen_at")
