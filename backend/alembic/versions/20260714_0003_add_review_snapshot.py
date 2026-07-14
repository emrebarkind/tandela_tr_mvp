"""add persisted review snapshot

Revision ID: 20260714_0003
Revises: 20260711_0002
Create Date: 2026-07-14 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260714_0003"
down_revision = "20260711_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("review_snapshot_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "review_snapshot_json")
