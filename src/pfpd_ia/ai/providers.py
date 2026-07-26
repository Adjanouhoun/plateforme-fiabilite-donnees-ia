from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pfpd_ia.ai.contracts import GeneratedIncidentExplanation, IncidentFactPackage


class ProviderError(RuntimeError):
    """Erreur contrôlée d'un fournisseur externe, sans détail sensible."""


class IncidentExplanationProvider(Protocol):
    provider_name: str
    model_name: str

    def generate(self, package: IncidentFactPackage) -> GeneratedIncidentExplanation: ...


@dataclass(frozen=True)
class ExplanationResult:
    explanation: GeneratedIncidentExplanation
    provider: str
    model: str | None
    generated_at: datetime
    is_ai_generated: bool
    degraded_reason: str | None


def deterministic_explanation(package: IncidentFactPackage) -> GeneratedIncidentExplanation:
    check = package.triggering_check
    facts_used = [
        f"Statut du contrôle {check.check_type} : {check.status}",
        f"Sévérité enregistrée : {package.severity}",
        f"Actif déclencheur : {package.triggering_asset.name}",
        f"Nombre d'actifs aval prouvés : {len(package.downstream_assets)}",
    ]
    unknowns = ["Cause racine non mesurée"]
    if not package.impact_documented:
        unknowns.append("Impact métier non documenté")

    return GeneratedIncidentExplanation(
        summary=(
            f"Le contrôle {check.check_type} est enregistré avec le statut "
            f"{check.status} et la sévérité {package.severity}."
        ),
        facts_used=facts_used,
        unknowns=unknowns,
        diagnostic_leads=[],
        declared_confidence="high",
    )


def explain_incident(
    package: IncidentFactPackage,
    *,
    provider: IncidentExplanationProvider | None,
    generated_at: datetime | None = None,
) -> ExplanationResult:
    timestamp = generated_at or datetime.now(UTC)
    if provider is None:
        return ExplanationResult(
            explanation=deterministic_explanation(package),
            provider="deterministic",
            model=None,
            generated_at=timestamp,
            is_ai_generated=False,
            degraded_reason="provider_not_configured",
        )

    try:
        explanation = provider.generate(package)
    except ProviderError:
        return ExplanationResult(
            explanation=deterministic_explanation(package),
            provider="deterministic",
            model=None,
            generated_at=timestamp,
            is_ai_generated=False,
            degraded_reason="provider_unavailable",
        )

    return ExplanationResult(
        explanation=explanation,
        provider=provider.provider_name,
        model=provider.model_name,
        generated_at=timestamp,
        is_ai_generated=True,
        degraded_reason=None,
    )
