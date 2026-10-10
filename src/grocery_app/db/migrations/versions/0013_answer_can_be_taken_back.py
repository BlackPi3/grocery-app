"""An answer can be taken back, and the memory with it.

Parham, 2026-10-08: he pressed Right on a spot check by accident and had
nothing to undo it with. An answer also teaches the memory what the printed
name means; taking the answer back must undo that too, or the accident
stays and a later answer turns the name into a family of two. Each answer
keeps the memory row as it was before it (`memory_before`); answers given
before this migration have none, and taking one back leaves the memory as
it is, as before.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_resolutions", sa.Column("memory_before", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("line_resolutions", "memory_before")
