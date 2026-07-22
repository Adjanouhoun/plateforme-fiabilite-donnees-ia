from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.incidents.service import acknowledge_incident, close_incident


@dataclass(frozen=True)
class PipelineSummary:
    pipeline_key: str
    display_name: str
    environment: str
    criticality: str
    owner: str
    expected_frequency_minutes: int | None
    latest_run_at: datetime | None
    latest_run_status: str | None
    latest_rows_read: int | None
    failed_checks: int
    not_measured_checks: int
    active_incidents: int
    highest_active_severity: str | None
    health_state: str


@dataclass(frozen=True)
class PortfolioKpis:
    window_days: int
    successful_runs: int
    completed_runs: int
    previous_successful_runs: int
    previous_completed_runs: int
    passed_checks: int
    measured_checks: int
    previous_passed_checks: int
    previous_measured_checks: int
    maximum_freshness_minutes: float | None
    previous_maximum_freshness_minutes: float | None
    active_incidents_by_severity: dict[str, int]
    average_closed_incident_minutes: float | None
    previous_average_closed_incident_minutes: float | None

    @property
    def run_success_rate(self) -> float | None:
        return _percentage(self.successful_runs, self.completed_runs)

    @property
    def previous_run_success_rate(self) -> float | None:
        return _percentage(self.previous_successful_runs, self.previous_completed_runs)

    @property
    def check_conformity_rate(self) -> float | None:
        return _percentage(self.passed_checks, self.measured_checks)

    @property
    def previous_check_conformity_rate(self) -> float | None:
        return _percentage(self.previous_passed_checks, self.previous_measured_checks)


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(100 * numerator / denominator, 1)


def derive_health_state(
    *, highest_active_severity: str | None, latest_run_status: str | None
) -> str:
    if highest_active_severity in {"critical", "error"}:
        return "incident_major"
    if highest_active_severity == "warning":
        return "warning"
    if latest_run_status is None:
        return "no_data"
    return "healthy"


PORTFOLIO_QUERY = text(
    """
    WITH latest_runs AS (
        SELECT DISTINCT ON (pipeline_id)
            pipeline_id,
            ended_at,
            started_at,
            status,
            rows_read
        FROM observability.pipeline_runs
        ORDER BY pipeline_id, started_at DESC, external_run_id DESC
    ),
    check_totals AS (
        SELECT
            pipeline_id,
            count(*) FILTER (WHERE status = 'failed') AS failed_checks,
            count(*) FILTER (WHERE status = 'not_measured') AS not_measured_checks
        FROM observability.quality_checks
        GROUP BY pipeline_id
    ),
    active_incidents AS (
        SELECT
            pipeline_id,
            count(*) AS active_incidents,
            max(
                CASE severity
                    WHEN 'critical' THEN 4
                    WHEN 'error' THEN 3
                    WHEN 'warning' THEN 2
                    WHEN 'info' THEN 1
                    ELSE 0
                END
            ) AS severity_rank
        FROM observability.incidents
        WHERE status IN ('open', 'acknowledged')
        GROUP BY pipeline_id
    )
    SELECT
        p.pipeline_key,
        p.display_name,
        p.environment,
        p.criticality,
        p.owner,
        p.expected_frequency_minutes,
        coalesce(lr.ended_at, lr.started_at) AS latest_run_at,
        lr.status AS latest_run_status,
        lr.rows_read AS latest_rows_read,
        coalesce(ct.failed_checks, 0) AS failed_checks,
        coalesce(ct.not_measured_checks, 0) AS not_measured_checks,
        coalesce(ai.active_incidents, 0) AS active_incidents,
        CASE ai.severity_rank
            WHEN 4 THEN 'critical'
            WHEN 3 THEN 'error'
            WHEN 2 THEN 'warning'
            WHEN 1 THEN 'info'
            ELSE NULL
        END AS highest_active_severity
    FROM observability.pipelines p
    LEFT JOIN latest_runs lr ON lr.pipeline_id = p.id
    LEFT JOIN check_totals ct ON ct.pipeline_id = p.id
    LEFT JOIN active_incidents ai ON ai.pipeline_id = p.id
    WHERE p.is_active = true
    ORDER BY p.display_name
    """
)

_SEVERITIES = ("critical", "error", "warning", "info")

_KPI_QUERY = text(
    """
    WITH selected_pipelines AS (
        SELECT id
        FROM observability.pipelines
        WHERE pipeline_key = ANY(:pipeline_keys)
    ),
    run_metrics AS (
        SELECT
            count(*) FILTER (
                WHERE started_at >= :current_start AND started_at < :end
                  AND status = 'succeeded'
            ) AS successful_runs,
            count(*) FILTER (
                WHERE started_at >= :current_start AND started_at < :end
                  AND ended_at IS NOT NULL
            ) AS completed_runs,
            count(*) FILTER (
                WHERE started_at >= :previous_start AND started_at < :current_start
                  AND status = 'succeeded'
            ) AS previous_successful_runs,
            count(*) FILTER (
                WHERE started_at >= :previous_start AND started_at < :current_start
                  AND ended_at IS NOT NULL
            ) AS previous_completed_runs
        FROM observability.pipeline_runs
        WHERE pipeline_id IN (SELECT id FROM selected_pipelines)
    ),
    check_metrics AS (
        SELECT
            count(*) FILTER (
                WHERE checked_at >= :current_start AND checked_at < :end
                  AND status = 'passed'
            ) AS passed_checks,
            count(*) FILTER (
                WHERE checked_at >= :current_start AND checked_at < :end
                  AND status IN ('passed', 'failed')
            ) AS measured_checks,
            count(*) FILTER (
                WHERE checked_at >= :previous_start AND checked_at < :current_start
                  AND status = 'passed'
            ) AS previous_passed_checks,
            count(*) FILTER (
                WHERE checked_at >= :previous_start AND checked_at < :current_start
                  AND status IN ('passed', 'failed')
            ) AS previous_measured_checks,
            max((observed_value ->> 'age_minutes')::double precision) FILTER (
                WHERE checked_at >= :current_start AND checked_at < :end
                  AND check_type = 'freshness'
                  AND observed_value ->> 'age_minutes' IS NOT NULL
            ) AS maximum_freshness_minutes,
            max((observed_value ->> 'age_minutes')::double precision) FILTER (
                WHERE checked_at >= :previous_start AND checked_at < :current_start
                  AND check_type = 'freshness'
                  AND observed_value ->> 'age_minutes' IS NOT NULL
            ) AS previous_maximum_freshness_minutes
        FROM observability.quality_checks
        WHERE pipeline_id IN (SELECT id FROM selected_pipelines)
    ),
    incident_metrics AS (
        SELECT
            avg(extract(epoch FROM (closed_at - opened_at)) / 60) FILTER (
                WHERE closed_at >= :current_start AND closed_at < :end
            ) AS average_closed_incident_minutes,
            avg(extract(epoch FROM (closed_at - opened_at)) / 60) FILTER (
                WHERE closed_at >= :previous_start AND closed_at < :current_start
            ) AS previous_average_closed_incident_minutes
        FROM observability.incidents
        WHERE pipeline_id IN (SELECT id FROM selected_pipelines)
          AND closed_at IS NOT NULL
    )
    SELECT
        rm.successful_runs,
        rm.completed_runs,
        rm.previous_successful_runs,
        rm.previous_completed_runs,
        cm.passed_checks,
        cm.measured_checks,
        cm.previous_passed_checks,
        cm.previous_measured_checks,
        cm.maximum_freshness_minutes,
        cm.previous_maximum_freshness_minutes,
        im.average_closed_incident_minutes,
        im.previous_average_closed_incident_minutes
    FROM run_metrics rm
    CROSS JOIN check_metrics cm
    CROSS JOIN incident_metrics im
    """
)

_ACTIVE_INCIDENTS_BY_SEVERITY_QUERY = text(
    """
    SELECT severity, count(*) AS incident_count
    FROM observability.incidents
    WHERE pipeline_id IN (
        SELECT id FROM observability.pipelines WHERE pipeline_key = ANY(:pipeline_keys)
    )
      AND status IN ('open', 'acknowledged')
    GROUP BY severity
    """
)


def list_pipeline_summaries(session: Session) -> list[PipelineSummary]:
    rows = session.execute(PORTFOLIO_QUERY).mappings().all()
    return [
        PipelineSummary(
            **row,
            health_state=derive_health_state(
                highest_active_severity=row["highest_active_severity"],
                latest_run_status=row["latest_run_status"],
            ),
        )
        for row in rows
    ]


def get_portfolio_kpis(
    session: Session,
    *,
    pipeline_keys: list[str],
    window_days: int,
    evaluated_at: datetime | None = None,
) -> PortfolioKpis:
    if window_days not in {7, 30}:
        raise ValueError("window_days must be 7 or 30")
    if not pipeline_keys:
        return PortfolioKpis(
            window_days=window_days,
            successful_runs=0,
            completed_runs=0,
            previous_successful_runs=0,
            previous_completed_runs=0,
            passed_checks=0,
            measured_checks=0,
            previous_passed_checks=0,
            previous_measured_checks=0,
            maximum_freshness_minutes=None,
            previous_maximum_freshness_minutes=None,
            active_incidents_by_severity={severity: 0 for severity in _SEVERITIES},
            average_closed_incident_minutes=None,
            previous_average_closed_incident_minutes=None,
        )

    end = evaluated_at or datetime.now(UTC)
    current_start = end - timedelta(days=window_days)
    previous_start = current_start - timedelta(days=window_days)
    parameters = {
        "pipeline_keys": pipeline_keys,
        "previous_start": previous_start,
        "current_start": current_start,
        "end": end,
    }
    row = session.execute(_KPI_QUERY, parameters).mappings().one()
    severities = session.execute(_ACTIVE_INCIDENTS_BY_SEVERITY_QUERY, parameters).mappings()
    active_by_severity = {severity: 0 for severity in _SEVERITIES}
    for severity_row in severities:
        active_by_severity[severity_row["severity"]] = severity_row["incident_count"]
    return PortfolioKpis(
        window_days=window_days,
        active_incidents_by_severity=active_by_severity,
        **row,
    )


def get_pipeline(session: Session, pipeline_key: str) -> dict[str, Any] | None:
    return (
        session.execute(
            text(
                """
            SELECT
                id, pipeline_key, display_name, description, owner, environment,
                expected_frequency_minutes, criticality, is_active
            FROM observability.pipelines
            WHERE pipeline_key = :pipeline_key
            """
            ),
            {"pipeline_key": pipeline_key},
        )
        .mappings()
        .one_or_none()
    )


def list_runs(session: Session, pipeline_key: str, limit: int = 100) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT
                    r.external_run_id, r.started_at, r.ended_at, r.status,
                    r.rows_read, r.rows_written, r.rows_rejected,
                    r.rows_unchanged, r.ingested_at
                FROM observability.pipeline_runs r
                JOIN observability.pipelines p ON p.id = r.pipeline_id
                WHERE p.pipeline_key = :pipeline_key
                ORDER BY r.started_at DESC, r.external_run_id DESC
                LIMIT :limit
                """
            ),
            {"pipeline_key": pipeline_key, "limit": limit},
        ).mappings()
    )


def list_checks(session: Session, pipeline_key: str, limit: int = 200) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT
                    q.id, q.check_type, q.status, q.severity, q.checked_at,
                    q.observed_value, q.expected_rule, q.evidence_reference,
                    a.name AS asset_name,
                    r.external_run_id
                FROM observability.quality_checks q
                JOIN observability.pipelines p ON p.id = q.pipeline_id
                JOIN observability.data_assets a ON a.id = q.asset_id
                LEFT JOIN observability.pipeline_runs r ON r.id = q.pipeline_run_id
                WHERE p.pipeline_key = :pipeline_key
                ORDER BY q.checked_at DESC, q.check_type
                LIMIT :limit
                """
            ),
            {"pipeline_key": pipeline_key, "limit": limit},
        ).mappings()
    )


def list_incidents(session: Session, pipeline_key: str) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT
                    i.id, i.title, i.severity, i.status, i.opened_at, i.closed_at,
                    i.business_impact, i.impact_origin,
                    q.check_type AS triggering_check_type
                FROM observability.incidents i
                JOIN observability.pipelines p ON p.id = i.pipeline_id
                LEFT JOIN observability.quality_checks q ON q.id = i.triggering_check_id
                WHERE p.pipeline_key = :pipeline_key
                ORDER BY i.opened_at DESC
                """
            ),
            {"pipeline_key": pipeline_key},
        ).mappings()
    )


def list_incident_events(session: Session, incident_id: uuid.UUID) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT event_type, occurred_at, actor, details
                FROM observability.incident_events
                WHERE incident_id = :incident_id
                ORDER BY occurred_at, id
                """
            ),
            {"incident_id": incident_id},
        ).mappings()
    )


def list_assets(session: Session, pipeline_key: str) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT
                    a.id, a.external_asset_id, a.name, a.asset_type,
                    a.source_system, a.logical_location, a.schema_contract,
                    a.owner, a.sensitivity, a.is_active
                FROM observability.data_assets a
                JOIN observability.pipelines p ON p.id = a.pipeline_id
                WHERE p.pipeline_key = :pipeline_key
                ORDER BY a.name
                """
            ),
            {"pipeline_key": pipeline_key},
        ).mappings()
    )


def list_lineage(session: Session, pipeline_key: str) -> list[dict[str, Any]]:
    return list(
        session.execute(
            text(
                """
                SELECT
                    source.name AS source_asset,
                    target.name AS target_asset,
                    edge.transformation_type,
                    edge.evidence_origin,
                    edge.observed_at
                FROM observability.lineage_edges edge
                JOIN observability.data_assets source ON source.id = edge.source_asset_id
                JOIN observability.data_assets target ON target.id = edge.target_asset_id
                JOIN observability.pipelines source_pipeline ON source_pipeline.id = source.pipeline_id
                JOIN observability.pipelines target_pipeline ON target_pipeline.id = target.pipeline_id
                WHERE source_pipeline.pipeline_key = :pipeline_key
                   OR target_pipeline.pipeline_key = :pipeline_key
                ORDER BY edge.observed_at DESC
                """
            ),
            {"pipeline_key": pipeline_key},
        ).mappings()
    )


def acknowledge(
    session_factory: sessionmaker[Session], *, incident_id: uuid.UUID, actor: str
) -> None:
    with session_factory.begin() as session:
        acknowledge_incident(
            session,
            incident_id=incident_id,
            occurred_at=datetime.now(UTC),
            actor=actor,
        )


def close(session_factory: sessionmaker[Session], *, incident_id: uuid.UUID, actor: str) -> None:
    with session_factory.begin() as session:
        close_incident(
            session,
            incident_id=incident_id,
            occurred_at=datetime.now(UTC),
            actor=actor,
        )
