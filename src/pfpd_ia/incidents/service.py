from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pfpd_ia.models import (
    CheckStatus,
    ImpactOrigin,
    Incident,
    IncidentEvent,
    IncidentStatus,
    QualityCheck,
)
from pfpd_ia.quality.rules import CheckEvaluation

SYSTEM_ACTOR = "quality-engine"
ACTIVE_STATUSES = (IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED)


def _add_event(
    session: Session,
    *,
    incident_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    actor: str,
    details: dict[str, object],
) -> None:
    session.add(
        IncidentEvent(
            incident_id=incident_id,
            event_type=event_type,
            occurred_at=occurred_at,
            actor=actor,
            details=details,
        )
    )


def _active_incident(session: Session, deduplication_key: str) -> Incident | None:
    return session.execute(
        select(Incident).where(
            Incident.deduplication_key == deduplication_key,
            Incident.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()


def record_check_and_reconcile_incident(
    session: Session,
    *,
    pipeline_id: uuid.UUID,
    asset_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None,
    idempotency_key: str,
    evaluation: CheckEvaluation,
    checked_at: datetime,
    incident_title: str,
) -> tuple[QualityCheck, Incident | None, bool]:
    check_id = uuid.uuid4()
    check_statement = (
        insert(QualityCheck)
        .values(
            id=check_id,
            pipeline_id=pipeline_id,
            asset_id=asset_id,
            pipeline_run_id=pipeline_run_id,
            idempotency_key=idempotency_key,
            check_type=evaluation.check_type,
            severity=evaluation.severity,
            observed_value=evaluation.observed_value,
            expected_rule=evaluation.expected_rule,
            status=evaluation.status,
            checked_at=checked_at,
            evidence_reference=evaluation.evidence_reference,
        )
        .on_conflict_do_nothing(
            index_elements=[QualityCheck.pipeline_id, QualityCheck.idempotency_key]
        )
        .returning(QualityCheck.id)
    )
    inserted_id = session.execute(check_statement).scalar_one_or_none()
    inserted = inserted_id is not None
    check = session.get(QualityCheck, inserted_id or check_id)
    if check is None:
        check = session.execute(
            select(QualityCheck).where(
                QualityCheck.pipeline_id == pipeline_id,
                QualityCheck.idempotency_key == idempotency_key,
            )
        ).scalar_one()

    deduplication_key = f"{asset_id}:{evaluation.check_type}"
    incident = _active_incident(session, deduplication_key)
    if not inserted:
        return check, incident, False

    if evaluation.status == CheckStatus.FAILED:
        if incident is None:
            incident_id = uuid.uuid4()
            incident_statement = (
                insert(Incident)
                .values(
                    id=incident_id,
                    pipeline_id=pipeline_id,
                    triggering_check_id=check.id,
                    deduplication_key=deduplication_key,
                    title=incident_title,
                    severity=evaluation.severity,
                    status=IncidentStatus.OPEN,
                    opened_at=checked_at,
                    business_impact=None,
                    impact_origin=ImpactOrigin.UNKNOWN,
                )
                .on_conflict_do_nothing(
                    index_elements=[Incident.deduplication_key],
                    index_where=text("status IN ('open', 'acknowledged')"),
                )
                .returning(Incident.id)
            )
            inserted_incident_id = session.execute(incident_statement).scalar_one_or_none()
            incident = session.get(Incident, inserted_incident_id or incident_id)
            if inserted_incident_id is not None:
                _add_event(
                    session,
                    incident_id=inserted_incident_id,
                    event_type="opened",
                    occurred_at=checked_at,
                    actor=SYSTEM_ACTOR,
                    details={"triggering_check_id": str(check.id)},
                )
            else:
                incident = _active_incident(session, deduplication_key)
        else:
            incident.triggering_check_id = check.id
            incident.severity = evaluation.severity
            _add_event(
                session,
                incident_id=incident.id,
                event_type="failure_observed",
                occurred_at=checked_at,
                actor=SYSTEM_ACTOR,
                details={"triggering_check_id": str(check.id)},
            )
    elif evaluation.status == CheckStatus.PASSED and incident is not None:
        incident.status = IncidentStatus.RESOLVED
        _add_event(
            session,
            incident_id=incident.id,
            event_type="resolved",
            occurred_at=checked_at,
            actor=SYSTEM_ACTOR,
            details={"resolving_check_id": str(check.id)},
        )

    return check, incident, True


def acknowledge_incident(
    session: Session, *, incident_id: uuid.UUID, occurred_at: datetime, actor: str
) -> Incident:
    incident = session.execute(
        select(Incident).where(Incident.id == incident_id).with_for_update()
    ).scalar_one()
    if incident.status != IncidentStatus.OPEN:
        raise ValueError("Seul un incident ouvert peut être acquitté")
    incident.status = IncidentStatus.ACKNOWLEDGED
    _add_event(
        session,
        incident_id=incident.id,
        event_type="acknowledged",
        occurred_at=occurred_at,
        actor=actor,
        details={},
    )
    return incident


def close_incident(
    session: Session, *, incident_id: uuid.UUID, occurred_at: datetime, actor: str
) -> Incident:
    incident = session.execute(
        select(Incident).where(Incident.id == incident_id).with_for_update()
    ).scalar_one()
    if incident.status != IncidentStatus.RESOLVED:
        raise ValueError("Seul un incident résolu peut être clôturé")
    incident.status = IncidentStatus.CLOSED
    incident.closed_at = occurred_at
    _add_event(
        session,
        incident_id=incident.id,
        event_type="closed",
        occurred_at=occurred_at,
        actor=actor,
        details={},
    )
    return incident
