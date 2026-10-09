"""A second photo of a receipt already in the history is not kept.

Parham, 2026-10-09: "a duplicate receipt shouldn't even be there." Until now
it stayed as a receipt flagged `is_duplicate`, out of the numbers but in the
list. Now the job that read it points at the receipt already there and says
`already_added`; the second copy is deleted and the flag goes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("already_added", sa.Boolean(), nullable=False,
                                    server_default="false"))
    # A job that read a duplicate now points at the first copy of that paper:
    # same shop, day and total, the earliest one not flagged.
    op.execute("""
        UPDATE jobs j SET already_added = true, receipt_id = (
            SELECT min(first.id) FROM receipts first
            WHERE NOT first.is_duplicate AND lower(first.store) = lower(d.store)
              AND first.date = d.date AND first.printed_total = d.printed_total)
        FROM receipts d WHERE j.receipt_id = d.id AND d.is_duplicate
    """)
    op.execute("DELETE FROM receipts WHERE is_duplicate")
    op.drop_column("receipts", "is_duplicate")


def downgrade() -> None:
    op.add_column("receipts", sa.Column("is_duplicate", sa.Boolean(), nullable=False,
                                        server_default="false"))
    op.drop_column("jobs", "already_added")
