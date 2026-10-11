"""What every model call cost.

Parham, 2026-10-11: see what processing a receipt costs, reading and finding
its items. Until now only a job's reading cost was kept (`jobs.cost_usd`);
those readings are copied in here as `reading` calls, so a month's reading
total is whole. What finding items cost before today was never written down.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("searches", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 5), nullable=True),
    )
    op.create_index("ix_model_calls_at", "model_calls", ["at"])
    op.create_index("ix_model_calls_job_id", "model_calls", ["job_id"])
    op.execute("""
        INSERT INTO model_calls (at, purpose, job_id, model, input_tokens, output_tokens,
                                 searches, cost_usd)
        SELECT coalesce(started_at, created_at), 'reading', id, model,
               coalesce((usage->>'promptTokenCount')::int, (usage->>'input_tokens')::int, 0),
               coalesce((usage->>'candidatesTokenCount')::int, 0)
                 + coalesce((usage->>'thoughtsTokenCount')::int, 0)
                 + coalesce((usage->>'output_tokens')::int, 0),
               0, cost_usd
        FROM jobs WHERE model IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("model_calls")
