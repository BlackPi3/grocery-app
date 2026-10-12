"""Sign in with Google: a user's Google address, and the sign-ins made with it.

2026-10-12, milestone "Ready for iOS": people sign in with Google on the web.
Invite-only: the owner adds a person's address on the People card, and only
that address gets in. Passwords keep working. A sign-in is a token the page
keeps, stored here as its sha256, with an end date.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(), nullable=True, unique=True))
    op.create_table(
        "sign_ins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sign_ins_user_id", "sign_ins", ["user_id"])


def downgrade() -> None:
    op.drop_table("sign_ins")
    op.drop_column("users", "email")
