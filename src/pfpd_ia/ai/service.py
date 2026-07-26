from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.ai.audit import persist_explanation
from pfpd_ia.ai.facts import build_incident_fact_package
from pfpd_ia.ai.providers import (
    ExplanationResult,
    IncidentExplanationProvider,
    explain_incident,
)


def generate_and_persist_explanation(
    session_factory: sessionmaker[Session],
    *,
    incident_id: uuid.UUID,
    provider: IncidentExplanationProvider | None,
) -> ExplanationResult:
    """Lit les faits, appelle le fournisseur hors transaction, puis audite le résultat."""

    with session_factory() as read_session:
        package = build_incident_fact_package(read_session, incident_id=incident_id)

    result = explain_incident(package, provider=provider)

    with session_factory.begin() as write_session:
        persist_explanation(write_session, package=package, result=result)

    return result
