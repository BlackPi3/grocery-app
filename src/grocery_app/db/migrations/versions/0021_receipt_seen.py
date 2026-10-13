"""When the shopper first opened a receipt: `receipts.seen_at`.

The owner, 2026-10-13: a finished receipt no longer opens by itself. A small
mark on the Receipts tab and on the receipt says a new one is there, and goes
when it is opened. Kept on the server, so the phone and the laptop agree.
Every receipt already there counts as seen: nobody starts with a page of marks.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE receipts SET seen_at = COALESCE(created_at, now())")


def downgrade() -> None:
    op.drop_column("receipts", "seen_at")
