from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictContract(BaseModel):
    """Base commune : aucun champ implicite ne traverse la frontière externe."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PipelineFacts(StrictContract):
    pipeline_key: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=80)
    criticality: Literal["low", "medium", "high", "critical"]


class AssetFacts(StrictContract):
    asset_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(min_length=1, max_length=80)
    source_system: str = Field(min_length=1, max_length=120)
    sensitivity: str = Field(min_length=1, max_length=80)


class CheckFacts(StrictContract):
    check_id: uuid.UUID
    check_type: str = Field(min_length=1, max_length=120)
    status: Literal["passed", "failed", "not_measured"]
    severity: Literal["info", "warning", "error", "critical"]
    checked_at: datetime
    observed_value: dict[str, Any] | None
    expected_rule: dict[str, Any]
    evidence_reference: str | None = Field(default=None, max_length=1000)


class DownstreamAssetFacts(StrictContract):
    asset_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(min_length=1, max_length=80)
    distance: int = Field(ge=1)


class IncidentEventFacts(StrictContract):
    event_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime


class IncidentFactPackage(StrictContract):
    """Contrat versionné des seuls faits autorisés à quitter la plateforme."""

    schema_version: Literal["1.0"] = "1.0"
    incident_id: uuid.UUID
    status: Literal["open", "acknowledged", "resolved", "closed"]
    severity: Literal["info", "warning", "error", "critical"]
    opened_at: datetime
    closed_at: datetime | None = None
    impact_origin: Literal["measured", "declared", "unknown"]
    impact_documented: bool
    pipeline: PipelineFacts
    triggering_asset: AssetFacts
    triggering_check: CheckFacts
    downstream_assets: list[DownstreamAssetFacts] = Field(default_factory=list)
    events: list[IncidentEventFacts] = Field(default_factory=list)


class GeneratedIncidentExplanation(StrictContract):
    """Sortie structurée attendue du fournisseur IA."""

    summary: str = Field(min_length=1, max_length=1500)
    facts_used: list[str] = Field(min_length=1, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    diagnostic_leads: list[str] = Field(default_factory=list, max_length=10)
    declared_confidence: Literal["low", "medium", "high"]
