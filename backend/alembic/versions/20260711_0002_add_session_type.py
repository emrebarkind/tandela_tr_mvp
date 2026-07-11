"""add session type

Revision ID: 20260711_0002
Revises: 20260628_0001
Create Date: 2026-07-11 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260711_0002"
down_revision = "20260628_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "session_type",
            sa.String(length=32),
            nullable=False,
            server_default="clinical_note",
        ),
    )
    op.create_index("ix_sessions_session_type", "sessions", ["session_type"])


def downgrade() -> None:
    op.drop_index("ix_sessions_session_type", table_name="sessions")
    op.drop_column("sessions", "session_type")
