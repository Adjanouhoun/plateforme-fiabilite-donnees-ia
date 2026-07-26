from types import SimpleNamespace

import pytest

from pfpd_ia.ai.contracts import GeneratedIncidentExplanation, IncidentFactPackage
from pfpd_ia.ai.gemini import (
    GeminiIncidentExplanationProvider,
    gemini_provider_from_settings,
)
from pfpd_ia.ai.providers import ProviderError
from pfpd_ia.config import Settings


def _package() -> IncidentFactPackage:
    return IncidentFactPackage.model_validate(
        {
            "incident_id": "10000000-0000-0000-0000-000000000001",
            "status": "open",
            "severity": "error",
            "opened_at": "2026-07-23T12:00:00Z",
            "impact_origin": "unknown",
            "impact_documented": False,
            "pipeline": {
                "pipeline_key": "mobility",
                "environment": "test",
                "criticality": "high",
            },
            "triggering_asset": {
                "asset_id": "20000000-0000-0000-0000-000000000002",
                "name": "fct_runs",
                "asset_type": "dbt_model",
                "source_system": "dbt_mobility",
                "sensitivity": "internal",
            },
            "triggering_check": {
                "check_id": "30000000-0000-0000-0000-000000000003",
                "check_type": "freshness",
                "status": "failed",
                "severity": "error",
                "checked_at": "2026-07-23T12:00:00Z",
                "observed_value": {"age_minutes": 480},
                "expected_rule": {"maximum_age_minutes": 360},
                "evidence_reference": "run:42",
            },
        }
    )


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)
        self.closed = False

    def close(self):
        self.closed = True


def test_gemini_adapter_requests_and_validates_structured_output() -> None:
    expected = GeneratedIncidentExplanation(
        summary="Le contrôle de fraîcheur a échoué.",
        facts_used=["Statut : failed"],
        unknowns=["Cause racine non mesurée"],
        diagnostic_leads=["Vérifier la dernière exécution réussie"],
        declared_confidence="medium",
    )
    client = FakeClient(SimpleNamespace(parsed=expected, text=None))
    received_keys = []

    def client_factory(*, api_key: str):
        received_keys.append(api_key)
        return client

    provider = GeminiIncidentExplanationProvider(
        api_key="local-test-key",
        model_name="gemini-3.5-flash-lite",
        client_factory=client_factory,
    )

    explanation = provider.generate(_package())

    assert explanation == expected
    assert received_keys == ["local-test-key"]
    assert client.closed is True
    assert client.models.calls[0]["model"] == "gemini-3.5-flash-lite"
    assert "local-test-key" not in client.models.calls[0]["contents"]
    config = client.models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.response_json_schema["additionalProperties"] is False
    diagnostic_schema = config.response_json_schema["properties"]["diagnostic_leads"]
    assert diagnostic_schema["minItems"] == 1
    assert diagnostic_schema["maxItems"] == 3


def test_gemini_adapter_rejects_an_empty_diagnostic_list() -> None:
    response = GeneratedIncidentExplanation(
        summary="Le contrôle de fraîcheur a échoué.",
        facts_used=["Statut : failed"],
        unknowns=["Cause racine non mesurée"],
        diagnostic_leads=[],
        declared_confidence="medium",
    )
    client = FakeClient(SimpleNamespace(parsed=response, text=None))
    provider = GeminiIncidentExplanationProvider(
        api_key="local-test-key",
        model_name="gemini-3.5-flash-lite",
        client_factory=lambda **_: client,
    )

    with pytest.raises(ProviderError, match="gemini_diagnostic_leads_invalid"):
        provider.generate(_package())

    assert client.closed is True


def test_gemini_is_disabled_without_explicit_activation_and_key() -> None:
    disabled = Settings(database_url="postgresql+psycopg://test")
    missing_key = Settings(
        database_url="postgresql+psycopg://test",
        gemini_enabled=True,
    )

    assert gemini_provider_from_settings(disabled) is None
    assert gemini_provider_from_settings(missing_key) is None
