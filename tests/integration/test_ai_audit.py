import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from pfpd_ia.ai.audit import persist_explanation
from pfpd_ia.ai.facts import build_incident_fact_package
from pfpd_ia.ai.providers import explain_incident
from pfpd_ia.ai.service import generate_and_persist_explanation
from pfpd_ia.database import get_session_factory
from pfpd_ia.models import (
    CheckStatus,
    Criticality,
    DataAsset,
    ImpactOrigin,
    Incident,
    IncidentExplanation,
    IncidentStatus,
    Pipeline,
    QualityCheck,
    Severity,
)

pytestmark = pytest.mark.integration


def test_explanations_are_appended_with_sanitized_audit_snapshots() -> None:
    now = datetime.now(UTC)
    factory = get_session_factory()

    with factory() as session, session.begin():
        pipeline = Pipeline(
            pipeline_key=f"test.ai.audit.{uuid.uuid4().hex}",
            display_name="Pipeline audit IA",
            owner="test",
            environment="test",
            expected_frequency_minutes=60,
            criticality=Criticality.HIGH,
            is_active=True,
        )
        session.add(pipeline)
        session.flush()
        asset = DataAsset(
            pipeline_id=pipeline.id,
            external_asset_id="source",
            name="source",
            asset_type="table",
            source_system="test",
            logical_location="test.source",
            schema_contract={},
            owner="test",
            sensitivity="internal",
            is_active=True,
        )
        session.add(asset)
        session.flush()
        check = QualityCheck(
            pipeline_id=pipeline.id,
            asset_id=asset.id,
            pipeline_run_id=None,
            idempotency_key=f"freshness:{uuid.uuid4().hex}",
            check_type="freshness",
            severity=Severity.ERROR,
            observed_value={"age_minutes": 480, "token": "must-not-be-stored"},
            expected_rule={"maximum_age_minutes": 360},
            status=CheckStatus.FAILED,
            checked_at=now,
            evidence_reference="run:42",
        )
        session.add(check)
        session.flush()
        incident = Incident(
            pipeline_id=pipeline.id,
            triggering_check_id=check.id,
            deduplication_key=f"{asset.id}:freshness",
            title="Incident audit",
            severity=Severity.ERROR,
            status=IncidentStatus.OPEN,
            opened_at=now,
            business_impact=None,
            impact_origin=ImpactOrigin.UNKNOWN,
        )
        session.add(incident)
        session.flush()

        package = build_incident_fact_package(session, incident_id=incident.id)
        result = explain_incident(package, provider=None, generated_at=now)
        first = persist_explanation(session, package=package, result=result)
        second = persist_explanation(session, package=package, result=result)

        records = list(
            session.scalars(
                select(IncidentExplanation)
                .where(IncidentExplanation.incident_id == incident.id)
                .order_by(IncidentExplanation.created_at, IncidentExplanation.id)
            )
        )
        session.refresh(incident)

        assert len(records) == 2
        assert first.id != second.id
        assert all(record.provider == "deterministic" for record in records)
        assert all(record.model is None for record in records)
        assert all(record.is_ai_generated is False for record in records)
        assert all(record.degraded_reason == "provider_not_configured" for record in records)
        assert records[0].input_schema_version == "1.0"
        assert records[0].output_schema_version == "1.0"
        assert records[0].fact_package["triggering_check"]["observed_value"]["token"] == (
            "[REDACTED]"
        )
        assert "facts_used" in records[0].explanation
        assert incident.status == IncidentStatus.OPEN

        session.rollback()


def test_orchestration_reads_generates_and_persists_in_separate_transactions() -> None:
    now = datetime.now(UTC)
    factory = get_session_factory()
    pipeline_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    check_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    with factory.begin() as session:
        session.add(
            Pipeline(
                id=pipeline_id,
                pipeline_key=f"test.ai.service.{uuid.uuid4().hex}",
                display_name="Pipeline orchestration IA",
                owner="test",
                environment="test",
                expected_frequency_minutes=60,
                criticality=Criticality.MEDIUM,
                is_active=True,
            )
        )
        session.flush()
        session.add(
            DataAsset(
                id=asset_id,
                pipeline_id=pipeline_id,
                external_asset_id="source",
                name="source",
                asset_type="table",
                source_system="test",
                logical_location="test.source",
                schema_contract={},
                owner="test",
                sensitivity="internal",
                is_active=True,
            )
        )
        session.flush()
        session.add(
            QualityCheck(
                id=check_id,
                pipeline_id=pipeline_id,
                asset_id=asset_id,
                pipeline_run_id=None,
                idempotency_key=f"freshness:{uuid.uuid4().hex}",
                check_type="freshness",
                severity=Severity.WARNING,
                observed_value={"age_minutes": 180},
                expected_rule={"maximum_age_minutes": 120},
                status=CheckStatus.FAILED,
                checked_at=now,
                evidence_reference="run:84",
            )
        )
        session.flush()
        session.add(
            Incident(
                id=incident_id,
                pipeline_id=pipeline_id,
                triggering_check_id=check_id,
                deduplication_key=f"{asset_id}:freshness",
                title="Incident orchestration",
                severity=Severity.WARNING,
                status=IncidentStatus.OPEN,
                opened_at=now,
                business_impact=None,
                impact_origin=ImpactOrigin.UNKNOWN,
            )
        )

    try:
        result = generate_and_persist_explanation(
            factory,
            incident_id=incident_id,
            provider=None,
        )

        with factory() as session:
            records = list(
                session.scalars(
                    select(IncidentExplanation).where(
                        IncidentExplanation.incident_id == incident_id
                    )
                )
            )
            incident_status = session.scalar(
                select(Incident.status).where(Incident.id == incident_id)
            )

        assert result.is_ai_generated is False
        assert result.degraded_reason == "provider_not_configured"
        assert len(records) == 1
        assert records[0].explanation["summary"] == result.explanation.summary
        assert incident_status == IncidentStatus.OPEN
    finally:
        with factory.begin() as session:
            session.execute(
                delete(IncidentExplanation).where(IncidentExplanation.incident_id == incident_id)
            )
            session.execute(delete(Incident).where(Incident.id == incident_id))
            session.execute(delete(QualityCheck).where(QualityCheck.id == check_id))
            session.execute(delete(DataAsset).where(DataAsset.id == asset_id))
            session.execute(delete(Pipeline).where(Pipeline.id == pipeline_id))
