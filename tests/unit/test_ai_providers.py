import uuid
from datetime import UTC, datetime

from pfpd_ia.ai.contracts import (
    AssetFacts,
    CheckFacts,
    IncidentFactPackage,
    PipelineFacts,
)
from pfpd_ia.ai.providers import ProviderError, explain_incident


def _package() -> IncidentFactPackage:
    now = datetime(2026, 7, 23, 12, tzinfo=UTC)
    return IncidentFactPackage(
        incident_id=uuid.uuid4(),
        status="open",
        severity="error",
        opened_at=now,
        impact_origin="unknown",
        impact_documented=False,
        pipeline=PipelineFacts(
            pipeline_key="mobility",
            environment="test",
            criticality="high",
        ),
        triggering_asset=AssetFacts(
            asset_id=uuid.uuid4(),
            name="fct_runs",
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
            evidence_reference="run:42",
        ),
    )


class UnavailableProvider:
    provider_name = "unavailable"
    model_name = "unavailable-model"

    def generate(self, package: IncidentFactPackage):
        raise ProviderError("quota_exhausted")


def test_missing_provider_uses_explicit_deterministic_mode() -> None:
    result = explain_incident(_package(), provider=None)

    assert result.provider == "deterministic"
    assert result.model is None
    assert result.is_ai_generated is False
    assert result.degraded_reason == "provider_not_configured"
    assert result.explanation.diagnostic_leads == []
    assert "Cause racine non mesurée" in result.explanation.unknowns
    assert "Impact métier non documenté" in result.explanation.unknowns


def test_provider_failure_never_prevents_a_factual_explanation() -> None:
    result = explain_incident(_package(), provider=UnavailableProvider())

    assert result.provider == "deterministic"
    assert result.is_ai_generated is False
    assert result.degraded_reason == "provider_unavailable"
    assert "freshness" in result.explanation.summary
