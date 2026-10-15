"""When the sender shared an upload with the developer: `jobs.shared_at`.

The owner, 2026-10-15: "I don't think it is good optics at all that I can
access their receipts ... we need consent." Another person's upload reaches
the developer only once they tap to share it; taking it back empties this.
Nothing already there counts as shared.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "shared_at")
