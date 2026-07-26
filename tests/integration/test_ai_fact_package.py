import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pfpd_ia.ai.facts import FactPackageUnavailable, build_incident_fact_package
from pfpd_ia.ai.sanitizer import REDACTED
from pfpd_ia.database import get_session_factory
from pfpd_ia.models import (
    CheckStatus,
    Criticality,
    DataAsset,
    ImpactOrigin,
    Incident,
    IncidentEvent,
    IncidentStatus,
    LineageEdge,
    Pipeline,
    QualityCheck,
    Severity,
)

pytestmark = pytest.mark.integration


def test_fact_package_is_built_from_common_model_and_proven_lineage() -> None:
    now = datetime.now(UTC)
    factory = get_session_factory()

    with factory() as session, session.begin():
        pipeline = Pipeline(
            pipeline_key=f"test.ai.facts.{uuid.uuid4().hex}",
            display_name="Pipeline IA",
            description="Test",
            owner="owner@example.test",
            environment="test",
            expected_frequency_minutes=60,
            criticality=Criticality.HIGH,
            is_active=True,
        )
        session.add(pipeline)
        session.flush()

        assets = [
            DataAsset(
                pipeline_id=pipeline.id,
                external_asset_id=f"asset-{index}",
                name=name,
                asset_type="dbt_model",
                source_system="dbt_test",
                logical_location=f"postgresql://reader:secret@db/{name}",
                schema_contract={},
                owner="owner@example.test",
                sensitivity="internal",
                is_active=True,
            )
            for index, name in enumerate(("source", "model", "exposure"))
        ]
        session.add_all(assets)
        session.flush()
        session.add_all(
            [
                LineageEdge(
                    source_asset_id=assets[0].id,
                    target_asset_id=assets[1].id,
                    transformation_type="dbt_dependency",
                    evidence_origin="dbt_manifest:source->model",
                    observed_at=now,
                ),
                LineageEdge(
                    source_asset_id=assets[1].id,
                    target_asset_id=assets[2].id,
                    transformation_type="dbt_dependency",
                    evidence_origin="dbt_manifest:model->exposure",
                    observed_at=now,
                ),
                LineageEdge(
                    source_asset_id=assets[2].id,
                    target_asset_id=assets[0].id,
                    transformation_type="test_cycle",
                    evidence_origin="test:cycle",
                    observed_at=now,
                ),
            ]
        )
        check = QualityCheck(
            pipeline_id=pipeline.id,
            asset_id=assets[0].id,
            pipeline_run_id=None,
            idempotency_key=f"freshness:{uuid.uuid4().hex}",
            check_type="freshness",
            severity=Severity.ERROR,
            observed_value={
                "age_minutes": 480,
                "api_key": "must-not-leave",
                "contact": "owner@example.test",
            },
            expected_rule={"maximum_age_minutes": 360},
            status=CheckStatus.FAILED,
            checked_at=now,
            evidence_reference="Bearer private-token run:42",
        )
        session.add(check)
        session.flush()
        incident = Incident(
            pipeline_id=pipeline.id,
            triggering_check_id=check.id,
            deduplication_key=f"{assets[0].id}:freshness",
            title="Texte libre non transmis",
            severity=Severity.ERROR,
            status=IncidentStatus.OPEN,
            opened_at=now,
            business_impact="Un utilisateur nommé ne doit pas être transmis",
            impact_origin=ImpactOrigin.DECLARED,
        )
        session.add(incident)
        session.flush()
        session.add_all(
            [
                IncidentEvent(
                    incident_id=incident.id,
                    event_type="opened",
                    occurred_at=now,
                    actor="owner@example.test",
                    details={"raw_error": "secret"},
                ),
                IncidentEvent(
                    incident_id=incident.id,
                    event_type="failure_observed",
                    occurred_at=now + timedelta(minutes=5),
                    actor="quality-engine",
                    details={},
                ),
            ]
        )
        session.flush()

        package = build_incident_fact_package(session, incident_id=incident.id)

        assert package.pipeline.pipeline_key == pipeline.pipeline_key
        assert package.impact_origin == "declared"
        assert package.impact_documented is True
        assert package.triggering_check.observed_value == {
            "age_minutes": 480,
            "api_key": REDACTED,
            "contact": REDACTED,
        }
        assert package.triggering_check.evidence_reference == f"{REDACTED} run:42"
        assert [(item.name, item.distance) for item in package.downstream_assets] == [
            ("model", 1),
            ("exposure", 2),
        ]
        assert [event.event_type for event in package.events] == [
            "opened",
            "failure_observed",
        ]
        serialized = package.model_dump(mode="json")
        assert "owner@example.test" not in str(serialized)
        assert "Un utilisateur nommé" not in str(serialized)
        assert "postgresql://" not in str(serialized)

        session.rollback()


def test_fact_package_fails_explicitly_for_missing_context() -> None:
    factory = get_session_factory()
    missing_id = uuid.uuid4()

    with (
        factory() as session,
        pytest.raises(FactPackageUnavailable, match="Incident introuvable"),
    ):
        build_incident_fact_package(session, incident_id=missing_id)
