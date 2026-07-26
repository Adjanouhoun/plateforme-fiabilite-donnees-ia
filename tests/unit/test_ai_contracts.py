import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pfpd_ia.ai.contracts import (
    AssetFacts,
    CheckFacts,
    DownstreamAssetFacts,
    GeneratedIncidentExplanation,
    IncidentEventFacts,
    IncidentFactPackage,
    PipelineFacts,
)
from pfpd_ia.ai.sanitizer import REDACTED, sanitize_fact_package


def _fact_package() -> IncidentFactPackage:
    now = datetime(2026, 7, 23, 10, 30, tzinfo=UTC)
    return IncidentFactPackage(
        incident_id=uuid.uuid4(),
        status="open",
        severity="error",
        opened_at=now,
        impact_origin="unknown",
        impact_documented=False,
        pipeline=PipelineFacts(
            pipeline_key="mobility",
            environment="local",
            criticality="high",
        ),
        triggering_asset=AssetFacts(
            asset_id=uuid.uuid4(),
            name="fact_trips",
            asset_type="dbt_model",
            source_system="dbt_mobility",
            sensitivity="internal",
        ),
        triggering_check=CheckFacts(
            check_id=uuid.uuid4(),
            check_type="freshness",
            status="failed",
            severity="error",
            checked_at=now,
            observed_value={"age_minutes": 480},
            expected_rule={"maximum_age_minutes": 360},
            evidence_reference="pipeline_run:run-42",
        ),
        downstream_assets=[
            DownstreamAssetFacts(
                asset_id=uuid.uuid4(),
                name="mobility_dashboard",
                asset_type="exposure",
                distance=1,
            )
        ],
        events=[IncidentEventFacts(event_type="opened", occurred_at=now)],
    )


def test_fact_package_excludes_free_text_and_operational_secrets() -> None:
    payload = _fact_package().model_dump(mode="json")

    assert payload["schema_version"] == "1.0"
    assert "title" not in payload
    assert "business_impact" not in payload
    assert "owner" not in payload["pipeline"]
    assert "logical_location" not in payload["triggering_asset"]
    assert "error_message" not in payload


def test_fact_package_forbids_uncontracted_fields() -> None:
    payload = _fact_package().model_dump(mode="python")
    payload["raw_error_message"] = "connection refused"

    with pytest.raises(ValidationError):
        IncidentFactPackage.model_validate(payload)


def test_sanitizer_redacts_secrets_dsn_bearer_and_email() -> None:
    package = _fact_package()
    payload = package.model_dump(mode="python")
    payload["triggering_check"]["observed_value"] = {
        "age_minutes": 480,
        "api_key": "key-123",
        "detail": "postgresql://reader:secret@db/mobility",
        "nested": ["Bearer abc.def", "owner@example.test"],
    }
    payload["triggering_check"]["evidence_reference"] = "token=visible run:42"

    sanitized = sanitize_fact_package(IncidentFactPackage.model_validate(payload))
    check = sanitized.triggering_check

    assert check.observed_value is not None
    assert check.observed_value["age_minutes"] == 480
    assert check.observed_value["api_key"] == REDACTED
    assert check.observed_value["detail"] == REDACTED
    assert check.observed_value["nested"] == [REDACTED, REDACTED]
    assert check.evidence_reference == f"{REDACTED} run:42"


def test_generated_explanation_requires_declared_facts_and_confidence() -> None:
    explanation = GeneratedIncidentExplanation(
        summary="Le contrôle de fraîcheur dépasse le seuil configuré.",
        facts_used=["Âge observé : 480 minutes", "Seuil : 360 minutes"],
        unknowns=["Cause racine non mesurée"],
        diagnostic_leads=["Vérifier la dernière exécution réussie"],
        declared_confidence="high",
    )

    assert explanation.declared_confidence == "high"

    with pytest.raises(ValidationError):
        GeneratedIncidentExplanation(
            summary="Conclusion sans référence",
            facts_used=[],
            declared_confidence="high",
        )
