"""add optional patient display name

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260714_0004"
down_revision = "20260714_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("display_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "display_name")
