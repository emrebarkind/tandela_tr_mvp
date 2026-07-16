"""add optional patient identity and medical history

Revision ID: 20260716_0005
Revises: 20260714_0004
Create Date: 2026-07-16 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260716_0005"
down_revision = "20260714_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("patients")}
    columns = (
        sa.Column("national_id", sa.String(length=32), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("occupation", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("referred_by", sa.String(length=255), nullable=True),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column("patients", column)
    if "patient_medical_histories" not in inspector.get_table_names():
        op.create_table(
            "patient_medical_histories",
            sa.Column("patient_id", sa.String(length=128), nullable=False),
            sa.Column("has_chronic_illness", sa.Boolean(), nullable=True),
            sa.Column("chronic_illness_detail", sa.Text(), nullable=True),
            sa.Column("takes_regular_medication", sa.Boolean(), nullable=True),
            sa.Column("regular_medication_detail", sa.Text(), nullable=True),
            sa.Column("has_drug_allergy", sa.Boolean(), nullable=True),
            sa.Column("drug_allergy_detail", sa.Text(), nullable=True),
            sa.Column("has_contagious_disease", sa.Boolean(), nullable=True),
            sa.Column("contagious_disease_detail", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
            sa.PrimaryKeyConstraint("patient_id"),
        )


def downgrade() -> None:
    op.drop_table("patient_medical_histories")
    op.drop_column("patients", "referred_by")
    op.drop_column("patients", "email")
    op.drop_column("patients", "phone")
    op.drop_column("patients", "address")
    op.drop_column("patients", "occupation")
    op.drop_column("patients", "date_of_birth")
    op.drop_column("patients", "national_id")
