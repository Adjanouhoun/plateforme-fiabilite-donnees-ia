import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from pfpd_ia.database import get_session_factory
from pfpd_ia.incidents.service import (
    acknowledge_incident,
    close_incident,
    record_check_and_reconcile_incident,
)
from pfpd_ia.models import (
    CheckStatus,
    Criticality,
    DataAsset,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Pipeline,
    QualityCheck,
    Severity,
)
from pfpd_ia.quality.rules import CheckEvaluation

pytestmark = pytest.mark.integration


def _failed_freshness() -> CheckEvaluation:
    return CheckEvaluation(
        check_type="freshness",
        severity=Severity.WARNING,
        status=CheckStatus.FAILED,
        observed_value={"age_minutes": 121},
        expected_rule={"warning_after_minutes": 120},
    )


def _passing_freshness() -> CheckEvaluation:
    return CheckEvaluation(
        check_type="freshness",
        severity=Severity.WARNING,
        status=CheckStatus.PASSED,
        observed_value={"age_minutes": 60},
        expected_rule={"warning_after_minutes": 120},
    )


def test_incident_lifecycle_is_idempotent_and_historized() -> None:
    factory = get_session_factory()
    pipeline_key = f"test.incident.{uuid.uuid4()}"
    now = datetime.now(UTC)

    with factory.begin() as session:
        pipeline = Pipeline(
            pipeline_key=pipeline_key,
            display_name="Incident test",
            owner="test",
            environment="test",
            expected_frequency_minutes=60,
            criticality=Criticality.LOW,
            is_active=True,
        )
        session.add(pipeline)
        session.flush()
        asset = DataAsset(
            pipeline_id=pipeline.id,
            external_asset_id="runs",
            name="Runs",
            asset_type="view",
            source_system="test",
            logical_location="test.runs",
            schema_contract={},
            owner="test",
            sensitivity="internal",
            is_active=True,
        )
        session.add(asset)
        session.flush()
        pipeline_id = pipeline.id
        asset_id = asset.id

        _, incident, inserted = record_check_and_reconcile_incident(
            session,
            pipeline_id=pipeline_id,
            asset_id=asset_id,
            pipeline_run_id=None,
            idempotency_key="freshness:slot-1",
            evaluation=_failed_freshness(),
            checked_at=now,
            incident_title="Freshness failed",
        )
        assert inserted is True
        assert incident is not None
        incident_id = incident.id

        _, repeated_incident, repeated_inserted = record_check_and_reconcile_incident(
            session,
            pipeline_id=pipeline_id,
            asset_id=asset_id,
            pipeline_run_id=None,
            idempotency_key="freshness:slot-1",
            evaluation=_failed_freshness(),
            checked_at=now,
            incident_title="Freshness failed",
        )
        assert repeated_inserted is False
        assert repeated_incident is not None
        assert repeated_incident.id == incident_id

        acknowledge_incident(
            session, incident_id=incident_id, occurred_at=now + timedelta(minutes=1), actor="tester"
        )
        _, same_incident, _ = record_check_and_reconcile_incident(
            session,
            pipeline_id=pipeline_id,
            asset_id=asset_id,
            pipeline_run_id=None,
            idempotency_key="freshness:slot-2",
            evaluation=_failed_freshness(),
            checked_at=now + timedelta(hours=1),
            incident_title="Freshness failed",
        )
        assert same_incident is not None
        assert same_incident.id == incident_id
        assert same_incident.status == IncidentStatus.ACKNOWLEDGED

        _, resolved, _ = record_check_and_reconcile_incident(
            session,
            pipeline_id=pipeline_id,
            asset_id=asset_id,
            pipeline_run_id=None,
            idempotency_key="freshness:slot-3",
            evaluation=_passing_freshness(),
            checked_at=now + timedelta(hours=2),
            incident_title="Freshness failed",
        )
        assert resolved is not None
        assert resolved.status == IncidentStatus.RESOLVED
        assert resolved.closed_at is None

        closed = close_incident(
            session, incident_id=incident_id, occurred_at=now + timedelta(hours=3), actor="tester"
        )
        assert closed.status == IncidentStatus.CLOSED

    with factory.begin() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QualityCheck)
                .where(QualityCheck.pipeline_id == pipeline_id)
            )
            == 3
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(Incident.pipeline_id == pipeline_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(IncidentEvent)
                .join(Incident, Incident.id == IncidentEvent.incident_id)
                .where(Incident.pipeline_id == pipeline_id)
            )
            == 5
        )

        session.execute(
            delete(IncidentEvent).where(
                IncidentEvent.incident_id.in_(
                    select(Incident.id).where(Incident.pipeline_id == pipeline_id)
                )
            )
        )
        session.execute(delete(Incident).where(Incident.pipeline_id == pipeline_id))
        session.execute(delete(QualityCheck).where(QualityCheck.pipeline_id == pipeline_id))
        session.execute(delete(DataAsset).where(DataAsset.pipeline_id == pipeline_id))
        session.execute(delete(Pipeline).where(Pipeline.id == pipeline_id))
