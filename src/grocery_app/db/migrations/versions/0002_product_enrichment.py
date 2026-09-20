"""What `enrich` adds to a product: nutrition, the enrichment record, and the
legacy free-form `extra` note.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("nutrition", "enrichment", "extra"):
        op.add_column("products", sa.Column(column, postgresql.JSONB(astext_type=sa.Text()),
                                            nullable=True))


def downgrade() -> None:
    for column in ("extra", "enrichment", "nutrition"):
        op.drop_column("products", column)
