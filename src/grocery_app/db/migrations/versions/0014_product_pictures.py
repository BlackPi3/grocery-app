"""A picture per product, for spot checks.

Parham, 2026-10-08: "Was it this one?" over a name rings no bell days later;
a photo of the pack does. `picture` is where it was found
(`{"url", "from", "page"}`, `grocery_app.pictures`); `picture_checked_at`
says the app has looked, so a product with no picture anywhere is not
looked up again on every pass.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("picture", JSONB(), nullable=True))
    op.add_column("products", sa.Column("picture_checked_at", sa.DateTime(timezone=True),
                                        nullable=True))


def downgrade() -> None:
    op.drop_column("products", "picture_checked_at")
    op.drop_column("products", "picture")
