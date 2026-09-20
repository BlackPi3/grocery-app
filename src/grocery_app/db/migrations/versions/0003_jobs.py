"""Extraction jobs, and the hash of the photo a receipt came from.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

COST = sa.Numeric(10, 5)


def upgrade() -> None:
    op.add_column("receipts", sa.Column("image_sha256", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_receipts_image_sha256"), "receipts", ["image_sha256"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("receipt_id", sa.Integer(),
                  sa.ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cost_usd", COST, nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_jobs_image_sha256"), "jobs", ["image_sha256"])


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_image_sha256"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_receipts_image_sha256"), table_name="receipts")
    op.drop_column("receipts", "image_sha256")
