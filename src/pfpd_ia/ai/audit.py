from __future__ import annotations

from sqlalchemy.orm import Session

from pfpd_ia.ai.contracts import IncidentFactPackage
from pfpd_ia.ai.providers import ExplanationResult
from pfpd_ia.models import IncidentExplanation

OUTPUT_SCHEMA_VERSION = "1.0"


def persist_explanation(
    session: Session,
    *,
    package: IncidentFactPackage,
    result: ExplanationResult,
) -> IncidentExplanation:
    """Ajoute une trace d'audit sans modifier l'incident source."""

    record = IncidentExplanation(
        incident_id=package.incident_id,
        provider=result.provider,
        model=result.model,
        generated_at=result.generated_at,
        is_ai_generated=result.is_ai_generated,
        degraded_reason=result.degraded_reason,
        input_schema_version=package.schema_version,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        fact_package=package.model_dump(mode="json"),
        explanation=result.explanation.model_dump(mode="json"),
    )
    session.add(record)
    session.flush()
    return record
