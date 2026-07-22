from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pfpd_ia.database import Base


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_MEASURED = "not_measured"


class IncidentStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ImpactOrigin(StrEnum):
    MEASURED = "measured"
    DECLARED = "declared"
    UNKNOWN = "unknown"


def enum_column(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Pipeline(TimestampMixin, Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        CheckConstraint("expected_frequency_minutes > 0", name="positive_frequency"),
        CheckConstraint("length(trim(pipeline_key)) > 0", name="non_empty_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_frequency_minutes: Mapped[int | None] = mapped_column(Integer)
    criticality: Mapped[Criticality] = mapped_column(
        enum_column(Criticality, "pipeline_criticality"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "external_run_id", name="uq_run_pipeline_external"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="valid_run_period"),
        CheckConstraint("rows_read IS NULL OR rows_read >= 0", name="non_negative_rows_read"),
        CheckConstraint(
            "rows_written IS NULL OR rows_written >= 0", name="non_negative_rows_written"
        ),
        CheckConstraint(
            "rows_rejected IS NULL OR rows_rejected >= 0", name="non_negative_rows_rejected"
        ),
        CheckConstraint(
            "rows_unchanged IS NULL OR rows_unchanged >= 0", name="non_negative_rows_unchanged"
        ),
        Index("ix_pipeline_runs_pipeline_started", "pipeline_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.pipelines.id", ondelete="RESTRICT"), nullable=False
    )
    external_run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(enum_column(RunStatus, "run_status"), nullable=False)
    rows_read: Mapped[int | None] = mapped_column(Integer)
    rows_written: Mapped[int | None] = mapped_column(Integer)
    rows_rejected: Mapped[int | None] = mapped_column(Integer)
    rows_unchanged: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataAsset(TimestampMixin, Base):
    __tablename__ = "data_assets"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "external_asset_id", name="uq_asset_pipeline_external"),
        Index("ix_data_assets_pipeline_active", "pipeline_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.pipelines.id", ondelete="RESTRICT"), nullable=False
    )
    external_asset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    logical_location: Mapped[str] = mapped_column(String(500), nullable=False)
    schema_contract: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QualityCheck(Base):
    __tablename__ = "quality_checks"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "idempotency_key", name="uq_check_pipeline_idempotency"),
        Index("ix_quality_checks_asset_checked", "asset_id", "checked_at"),
        Index("ix_quality_checks_pipeline_status", "pipeline_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.pipelines.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.data_assets.id", ondelete="RESTRICT"), nullable=False
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observability.pipeline_runs.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, "quality_severity"), nullable=False
    )
    observed_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expected_rule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[CheckStatus] = mapped_column(
        enum_column(CheckStatus, "check_status"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(1000))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at", name="valid_incident_period"
        ),
        Index("ix_incidents_pipeline_status", "pipeline_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.pipelines.id", ondelete="RESTRICT"), nullable=False
    )
    triggering_check_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observability.quality_checks.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, "incident_severity"), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        enum_column(IncidentStatus, "incident_status"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_impact: Mapped[str | None] = mapped_column(Text)
    impact_origin: Mapped[ImpactOrigin] = mapped_column(
        enum_column(ImpactOrigin, "impact_origin"), nullable=False
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (Index("ix_incident_events_incident_occurred", "incident_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.incidents.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "transformation_type",
            "evidence_origin",
            name="uq_lineage_evidence",
        ),
        CheckConstraint("source_asset_id <> target_asset_id", name="distinct_lineage_assets"),
        Index("ix_lineage_edges_target", "target_asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.data_assets.id", ondelete="RESTRICT"), nullable=False
    )
    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observability.data_assets.id", ondelete="RESTRICT"), nullable=False
    )
    transformation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_origin: Mapped[str] = mapped_column(String(500), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
