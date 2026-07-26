"""Store auditable incident explanations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "observability"


def upgrade() -> None:
    op.create_table(
        "incident_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("model", sa.String(255)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False),
        sa.Column("degraded_reason", sa.String(120)),
        sa.Column("input_schema_version", sa.String(20), nullable=False),
        sa.Column("output_schema_version", sa.String(20), nullable=False),
        sa.Column("fact_package", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0",
            name="ck_incident_explanations_non_empty_provider",
        ),
        sa.CheckConstraint(
            "length(trim(input_schema_version)) > 0",
            name="ck_incident_explanations_non_empty_input_schema",
        ),
        sa.CheckConstraint(
            "length(trim(output_schema_version)) > 0",
            name="ck_incident_explanations_non_empty_output_schema",
        ),
        sa.CheckConstraint(
            "is_ai_generated = false OR model IS NOT NULL",
            name="ck_incident_explanations_ai_generation_has_model",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            [f"{SCHEMA}.incidents.id"],
            name="fk_incident_explanations_incident_id_incidents",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incident_explanations"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_incident_explanations_incident_generated",
        "incident_explanations",
        ["incident_id", "generated_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incident_explanations_incident_generated",
        table_name="incident_explanations",
        schema=SCHEMA,
    )
    op.drop_table("incident_explanations", schema=SCHEMA)
