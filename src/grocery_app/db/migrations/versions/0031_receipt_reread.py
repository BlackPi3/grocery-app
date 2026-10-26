"""How often the server has read a receipt's waiting lines again, and when
last: `receipts.reread_tries`, `receipts.reread_at` (`api.matching.reread_waiting`).

Kept in the database, not the server's memory: the server stops after a
quiet spell and starts on the next visit, and a count that started anew
each time would pay for the same failing search many times a day.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("reread_tries", sa.Integer(), nullable=False,
                                        server_default="0"))
    op.add_column("receipts", sa.Column("reread_at", sa.DateTime(timezone=True),
                                        nullable=True))


def downgrade() -> None:
    op.drop_column("receipts", "reread_at")
    op.drop_column("receipts", "reread_tries")
