"""Create the initial observability schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "observability"


def uuid_column(name: str = "id") -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def text_enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(SCHEMA))

    op.create_table(
        "pipelines",
        uuid_column(),
        sa.Column("pipeline_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(80), nullable=False),
        sa.Column("expected_frequency_minutes", sa.Integer()),
        sa.Column(
            "criticality",
            text_enum("pipeline_criticality", "low", "medium", "high", "critical"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "expected_frequency_minutes > 0", name="ck_pipelines_positive_frequency"
        ),
        sa.CheckConstraint("length(trim(pipeline_key)) > 0", name="ck_pipelines_non_empty_key"),
        sa.PrimaryKeyConstraint("id", name="pk_pipelines"),
        sa.UniqueConstraint("pipeline_key", name="uq_pipelines_pipeline_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "pipeline_runs",
        uuid_column(),
        uuid_column("pipeline_id"),
        sa.Column("external_run_id", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column(
            "status",
            text_enum(
                "run_status", "pending", "running", "succeeded", "failed", "cancelled", "unknown"
            ),
            nullable=False,
        ),
        sa.Column("rows_read", sa.Integer()),
        sa.Column("rows_written", sa.Integer()),
        sa.Column("rows_rejected", sa.Integer()),
        sa.Column("rows_unchanged", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="ck_pipeline_runs_valid_run_period"
        ),
        sa.CheckConstraint(
            "rows_read IS NULL OR rows_read >= 0", name="ck_pipeline_runs_non_negative_rows_read"
        ),
        sa.CheckConstraint(
            "rows_written IS NULL OR rows_written >= 0",
            name="ck_pipeline_runs_non_negative_rows_written",
        ),
        sa.CheckConstraint(
            "rows_rejected IS NULL OR rows_rejected >= 0",
            name="ck_pipeline_runs_non_negative_rows_rejected",
        ),
        sa.CheckConstraint(
            "rows_unchanged IS NULL OR rows_unchanged >= 0",
            name="ck_pipeline_runs_non_negative_rows_unchanged",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            [f"{SCHEMA}.pipelines.id"],
            name="fk_pipeline_runs_pipeline_id_pipelines",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
        sa.UniqueConstraint("pipeline_id", "external_run_id", name="uq_run_pipeline_external"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_pipeline_runs_pipeline_started",
        "pipeline_runs",
        ["pipeline_id", "started_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "data_assets",
        uuid_column(),
        uuid_column("pipeline_id"),
        sa.Column("external_asset_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(80), nullable=False),
        sa.Column("source_system", sa.String(120), nullable=False),
        sa.Column("logical_location", sa.String(500), nullable=False),
        sa.Column("schema_contract", sa.JSON()),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("sensitivity", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            [f"{SCHEMA}.pipelines.id"],
            name="fk_data_assets_pipeline_id_pipelines",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_assets"),
        sa.UniqueConstraint("pipeline_id", "external_asset_id", name="uq_asset_pipeline_external"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_data_assets_pipeline_active", "data_assets", ["pipeline_id", "is_active"], schema=SCHEMA
    )

    op.create_table(
        "quality_checks",
        uuid_column(),
        uuid_column("pipeline_id"),
        uuid_column("asset_id"),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("check_type", sa.String(120), nullable=False),
        sa.Column(
            "severity",
            text_enum("quality_severity", "info", "warning", "error", "critical"),
            nullable=False,
        ),
        sa.Column("observed_value", sa.JSON()),
        sa.Column("expected_rule", sa.JSON(), nullable=False),
        sa.Column(
            "status", text_enum("check_status", "passed", "failed", "not_measured"), nullable=False
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_reference", sa.String(1000)),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            [f"{SCHEMA}.data_assets.id"],
            name="fk_quality_checks_asset_id_data_assets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            [f"{SCHEMA}.pipelines.id"],
            name="fk_quality_checks_pipeline_id_pipelines",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            [f"{SCHEMA}.pipeline_runs.id"],
            name="fk_quality_checks_pipeline_run_id_pipeline_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quality_checks"),
        sa.UniqueConstraint("pipeline_id", "idempotency_key", name="uq_check_pipeline_idempotency"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_quality_checks_asset_checked",
        "quality_checks",
        ["asset_id", "checked_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_quality_checks_pipeline_status",
        "quality_checks",
        ["pipeline_id", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "incidents",
        uuid_column(),
        uuid_column("pipeline_id"),
        sa.Column("triggering_check_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "severity",
            text_enum("incident_severity", "info", "warning", "error", "critical"),
            nullable=False,
        ),
        sa.Column(
            "status",
            text_enum("incident_status", "open", "acknowledged", "resolved", "closed"),
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("business_impact", sa.Text()),
        sa.Column(
            "impact_origin",
            text_enum("impact_origin", "measured", "declared", "unknown"),
            nullable=False,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at", name="ck_incidents_valid_incident_period"
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            [f"{SCHEMA}.pipelines.id"],
            name="fk_incidents_pipeline_id_pipelines",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triggering_check_id"],
            [f"{SCHEMA}.quality_checks.id"],
            name="fk_incidents_triggering_check_id_quality_checks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incidents"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_incidents_pipeline_status", "incidents", ["pipeline_id", "status"], schema=SCHEMA
    )

    op.create_table(
        "incident_events",
        uuid_column(),
        uuid_column("incident_id"),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            [f"{SCHEMA}.incidents.id"],
            name="fk_incident_events_incident_id_incidents",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incident_events"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_incident_events_incident_occurred",
        "incident_events",
        ["incident_id", "occurred_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "lineage_edges",
        uuid_column(),
        uuid_column("source_asset_id"),
        uuid_column("target_asset_id"),
        sa.Column("transformation_type", sa.String(120), nullable=False),
        sa.Column("evidence_origin", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_asset_id <> target_asset_id", name="ck_lineage_edges_distinct_lineage_assets"
        ),
        sa.ForeignKeyConstraint(
            ["source_asset_id"],
            [f"{SCHEMA}.data_assets.id"],
            name="fk_lineage_edges_source_asset_id_data_assets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_asset_id"],
            [f"{SCHEMA}.data_assets.id"],
            name="fk_lineage_edges_target_asset_id_data_assets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lineage_edges"),
        sa.UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "transformation_type",
            "evidence_origin",
            name="uq_lineage_evidence",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_lineage_edges_target", "lineage_edges", ["target_asset_id"], schema=SCHEMA)


def downgrade() -> None:
    for table in (
        "lineage_edges",
        "incident_events",
        "incidents",
        "quality_checks",
        "data_assets",
        "pipeline_runs",
        "pipelines",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(sa.schema.DropSchema(SCHEMA))
