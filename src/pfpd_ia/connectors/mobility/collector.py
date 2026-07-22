from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.connectors.mobility.config import (
    EXPECTED_SOURCE_COLUMNS,
    PIPELINE_DEFINITIONS,
    MobilitySettings,
    PipelineDefinition,
)
from pfpd_ia.connectors.mobility.sanitizer import sanitize_error_message
from pfpd_ia.incidents.service import record_check_and_reconcile_incident
from pfpd_ia.models import (
    CheckStatus,
    DataAsset,
    Incident,
    IncidentStatus,
    Pipeline,
    PipelineRun,
    RunStatus,
)
from pfpd_ia.quality.rules import (
    CheckEvaluation,
    evaluate_consistency,
    evaluate_freshness,
    evaluate_schema,
    evaluate_uniqueness,
    evaluate_volume,
)

SOURCE_SCHEMA_QUERY = text(
    """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'schema_analytics'
      AND table_name = 'fct_pipeline_runs'
    ORDER BY ordinal_position
    """
)

SOURCE_DAGS_QUERY = text(
    """
    SELECT DISTINCT dag_id
    FROM schema_analytics.fct_pipeline_runs
    ORDER BY dag_id
    """
)

SOURCE_RUNS_QUERY = text(
    """
    SELECT
        pipeline_run_id,
        dag_id,
        started_at,
        finished_at,
        status,
        records_received,
        changed_record_count,
        records_unchanged,
        error_message
    FROM schema_analytics.fct_pipeline_runs
    WHERE dag_id IN (:velib_dag_id, :traffic_dag_id)
    ORDER BY started_at, pipeline_run_id
    """
)

SOURCE_UNIQUENESS_QUERY = text(
    """
    SELECT
        dag_id,
        count(*) AS total_count,
        count(DISTINCT pipeline_run_id) AS distinct_count
    FROM schema_analytics.fct_pipeline_runs
    WHERE dag_id IN (:velib_dag_id, :traffic_dag_id)
    GROUP BY dag_id
    """
)


class MobilityRunRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pipeline_run_id: str
    dag_id: str
    started_at: datetime
    finished_at: datetime
    status: str
    records_received: int
    changed_record_count: int
    records_unchanged: int
    error_message: str | None


@dataclass(frozen=True)
class CollectionReport:
    source_rows: int
    inserted_runs: int
    duplicate_runs: int
    unknown_dag_ids: tuple[str, ...]
    unknown_statuses: tuple[str, ...]
    source_read_only: bool
    inserted_checks: int
    failed_checks: int
    not_measured_checks: int
    active_incidents: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_source_engine(settings: MobilitySettings) -> Engine:
    return create_engine(
        settings.mobility_database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={
            "application_name": "pfpd_ia_mobility_reader",
            "connect_timeout": 10,
        },
    )


@dataclass(frozen=True)
class SourceSnapshot:
    runs: tuple[MobilityRunRecord, ...]
    unknown_dag_ids: tuple[str, ...]
    source_read_only: bool
    actual_columns: dict[str, str]
    uniqueness_by_dag: dict[str, tuple[int, int]]


def _source_parameters() -> dict[str, str]:
    return {
        "velib_dag_id": PIPELINE_DEFINITIONS[0].dag_id,
        "traffic_dag_id": PIPELINE_DEFINITIONS[1].dag_id,
    }


def _read_source_runs(source_engine: Engine) -> SourceSnapshot:
    allowed_dags = {definition.dag_id for definition in PIPELINE_DEFINITIONS}
    with source_engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        source_read_only = connection.execute(text("SHOW transaction_read_only")).scalar_one()
        if source_read_only != "on":
            raise RuntimeError("La transaction source Mobility n'est pas en lecture seule")

        actual_columns = dict(connection.execute(SOURCE_SCHEMA_QUERY).all())
        schema_evaluation = evaluate_schema(
            actual_columns=actual_columns,
            expected_columns=EXPECTED_SOURCE_COLUMNS,
        )
        if schema_evaluation.status == CheckStatus.FAILED:
            return SourceSnapshot(
                runs=(),
                unknown_dag_ids=(),
                source_read_only=True,
                actual_columns=actual_columns,
                uniqueness_by_dag={},
            )

        observed_dags = set(connection.execute(SOURCE_DAGS_QUERY).scalars())
        unknown_dags = tuple(sorted(observed_dags - allowed_dags))
        parameters = _source_parameters()
        rows = connection.execute(SOURCE_RUNS_QUERY, parameters).mappings().all()
        uniqueness_by_dag = {
            row.dag_id: (row.total_count, row.distinct_count)
            for row in connection.execute(SOURCE_UNIQUENESS_QUERY, parameters)
        }

    return SourceSnapshot(
        runs=tuple(MobilityRunRecord.model_validate(row) for row in rows),
        unknown_dag_ids=unknown_dags,
        source_read_only=True,
        actual_columns=actual_columns,
        uniqueness_by_dag=uniqueness_by_dag,
    )


def _upsert_pipeline(
    session: Session,
    definition: PipelineDefinition,
    settings: MobilitySettings,
):
    statement = (
        insert(Pipeline)
        .values(
            pipeline_key=definition.pipeline_key,
            display_name=definition.display_name,
            description=definition.description,
            owner=settings.mobility_owner,
            environment=settings.mobility_environment,
            expected_frequency_minutes=definition.expected_frequency_minutes,
            criticality=settings.mobility_criticality,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Pipeline.pipeline_key],
            set_={
                "display_name": definition.display_name,
                "description": definition.description,
                "owner": settings.mobility_owner,
                "environment": settings.mobility_environment,
                "expected_frequency_minutes": definition.expected_frequency_minutes,
                "criticality": settings.mobility_criticality,
                "is_active": True,
            },
        )
        .returning(Pipeline.id)
    )
    return session.execute(statement).scalar_one()


def _normalize_status(source_status: str) -> RunStatus:
    return {
        "success": RunStatus.SUCCEEDED,
        "failed": RunStatus.FAILED,
    }.get(source_status, RunStatus.UNKNOWN)


def _upsert_asset(
    session: Session,
    *,
    pipeline_id,
    definition: PipelineDefinition,
    settings: MobilitySettings,
):
    schema_contract = {
        "columns": {
            column: list(allowed_types) for column, allowed_types in EXPECTED_SOURCE_COLUMNS.items()
        },
        "filter": {"dag_id": definition.dag_id},
        "dbt_unique_id": definition.monitoring_asset_dbt_unique_id,
    }
    statement = (
        insert(DataAsset)
        .values(
            pipeline_id=pipeline_id,
            external_asset_id=definition.asset_external_id,
            name=f"Exécutions {definition.display_name}",
            asset_type="view",
            source_system="mobility",
            logical_location=definition.asset_logical_location,
            schema_contract=schema_contract,
            owner=settings.mobility_owner,
            sensitivity="internal",
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[DataAsset.pipeline_id, DataAsset.external_asset_id],
            set_={
                "name": f"Exécutions {definition.display_name}",
                "asset_type": "view",
                "source_system": "mobility",
                "logical_location": definition.asset_logical_location,
                "schema_contract": schema_contract,
                "owner": settings.mobility_owner,
                "sensitivity": "internal",
                "is_active": True,
            },
        )
        .returning(DataAsset.id)
    )
    return session.execute(statement).scalar_one()


def _with_evidence(evaluation: CheckEvaluation, definition: PipelineDefinition) -> CheckEvaluation:
    return replace(evaluation, evidence_reference=definition.asset_logical_location)


def _record_evaluation(
    session: Session,
    *,
    pipeline_id,
    asset_id,
    pipeline_run_id,
    idempotency_key: str,
    evaluation: CheckEvaluation,
    checked_at: datetime,
    definition: PipelineDefinition,
) -> tuple[bool, CheckStatus]:
    _, _, inserted = record_check_and_reconcile_incident(
        session,
        pipeline_id=pipeline_id,
        asset_id=asset_id,
        pipeline_run_id=pipeline_run_id,
        idempotency_key=idempotency_key,
        evaluation=_with_evidence(evaluation, definition),
        checked_at=checked_at,
        incident_title=f"{definition.display_name} — contrôle {evaluation.check_type} en échec",
    )
    return inserted, evaluation.status


def collect_mobility_runs(
    source_engine: Engine,
    target_session_factory: sessionmaker[Session],
    settings: MobilitySettings,
    evaluated_at: datetime | None = None,
) -> CollectionReport:
    snapshot = _read_source_runs(source_engine)
    source_runs = snapshot.runs
    evaluated_at = evaluated_at or datetime.now(UTC)
    evaluation_slot = evaluated_at.replace(minute=0, second=0, microsecond=0).isoformat()
    definitions_by_dag = {definition.dag_id: definition for definition in PIPELINE_DEFINITIONS}
    unknown_statuses = tuple(
        sorted({run.status for run in source_runs if run.status not in {"success", "failed"}})
    )

    inserted_runs = 0
    inserted_checks = 0
    failed_checks = 0
    not_measured_checks = 0
    with target_session_factory.begin() as session:
        pipeline_ids = {
            definition.dag_id: _upsert_pipeline(session, definition, settings)
            for definition in PIPELINE_DEFINITIONS
        }
        asset_ids = {
            definition.dag_id: _upsert_asset(
                session,
                pipeline_id=pipeline_ids[definition.dag_id],
                definition=definition,
                settings=settings,
            )
            for definition in PIPELINE_DEFINITIONS
        }

        for definition in PIPELINE_DEFINITIONS:
            pipeline_id = pipeline_ids[definition.dag_id]
            asset_id = asset_ids[definition.dag_id]
            evaluations = [
                (
                    f"schema:{evaluation_slot}",
                    evaluate_schema(
                        actual_columns=snapshot.actual_columns,
                        expected_columns=EXPECTED_SOURCE_COLUMNS,
                    ),
                )
            ]
            uniqueness = snapshot.uniqueness_by_dag.get(definition.dag_id)
            uniqueness_evaluation = evaluate_uniqueness(
                total_count=uniqueness[0] if uniqueness is not None else None,
                distinct_count=uniqueness[1] if uniqueness is not None else None,
            )
            evaluations.append((f"uniqueness:{evaluation_slot}", uniqueness_evaluation))

            for idempotency_key, evaluation in evaluations:
                inserted, status = _record_evaluation(
                    session,
                    pipeline_id=pipeline_id,
                    asset_id=asset_id,
                    pipeline_run_id=None,
                    idempotency_key=idempotency_key,
                    evaluation=evaluation,
                    checked_at=evaluated_at,
                    definition=definition,
                )
                inserted_checks += int(inserted)
                failed_checks += int(inserted and status == CheckStatus.FAILED)
                not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)

        target_run_ids = {}
        for source_run in source_runs:
            definition = definitions_by_dag[source_run.dag_id]
            statement = (
                insert(PipelineRun)
                .values(
                    pipeline_id=pipeline_ids[definition.dag_id],
                    external_run_id=source_run.pipeline_run_id,
                    started_at=source_run.started_at,
                    ended_at=source_run.finished_at,
                    status=_normalize_status(source_run.status),
                    rows_read=source_run.records_received,
                    rows_written=source_run.changed_record_count,
                    rows_rejected=None,
                    rows_unchanged=source_run.records_unchanged,
                    error_message=sanitize_error_message(
                        source_run.error_message,
                        settings.mobility_error_max_length,
                    ),
                )
                .on_conflict_do_nothing(
                    index_elements=[PipelineRun.pipeline_id, PipelineRun.external_run_id]
                )
                .returning(PipelineRun.id)
            )
            inserted_run_id = session.execute(statement).scalar_one_or_none()
            if inserted_run_id is not None:
                inserted_runs += 1
                target_run_ids[(definition.dag_id, source_run.pipeline_run_id)] = inserted_run_id
            else:
                target_run_ids[(definition.dag_id, source_run.pipeline_run_id)] = session.execute(
                    select(PipelineRun.id).where(
                        PipelineRun.pipeline_id == pipeline_ids[definition.dag_id],
                        PipelineRun.external_run_id == source_run.pipeline_run_id,
                    )
                ).scalar_one()

        for definition in PIPELINE_DEFINITIONS:
            pipeline_runs = [run for run in source_runs if run.dag_id == definition.dag_id]
            successful_runs = [run for run in pipeline_runs if run.status == "success"]
            latest_success_at = max(
                (run.finished_at for run in successful_runs),
                default=None,
            )
            snapshot_evaluation = evaluate_freshness(
                latest_success_at=latest_success_at,
                evaluated_at=evaluated_at,
            )
            inserted, status = _record_evaluation(
                session,
                pipeline_id=pipeline_ids[definition.dag_id],
                asset_id=asset_ids[definition.dag_id],
                pipeline_run_id=None,
                idempotency_key=f"freshness:{evaluation_slot}",
                evaluation=snapshot_evaluation,
                checked_at=evaluated_at,
                definition=definition,
            )
            inserted_checks += int(inserted)
            failed_checks += int(inserted and status == CheckStatus.FAILED)
            not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)

            previous_successful_volumes: list[int] = []
            for source_run in sorted(
                pipeline_runs, key=lambda run: (run.started_at, run.pipeline_run_id)
            ):
                target_run_id = target_run_ids[(definition.dag_id, source_run.pipeline_run_id)]
                consistency = evaluate_consistency(
                    rows_read=source_run.records_received,
                    rows_written=source_run.changed_record_count,
                    rows_unchanged=source_run.records_unchanged,
                )
                volume = evaluate_volume(
                    current_volume=(
                        source_run.records_received if source_run.status == "success" else None
                    ),
                    reference_volumes=list(reversed(previous_successful_volumes[-5:])),
                )
                for evaluation in (consistency, volume):
                    inserted, status = _record_evaluation(
                        session,
                        pipeline_id=pipeline_ids[definition.dag_id],
                        asset_id=asset_ids[definition.dag_id],
                        pipeline_run_id=target_run_id,
                        idempotency_key=f"{evaluation.check_type}:{source_run.pipeline_run_id}",
                        evaluation=evaluation,
                        checked_at=source_run.finished_at,
                        definition=definition,
                    )
                    inserted_checks += int(inserted)
                    failed_checks += int(inserted and status == CheckStatus.FAILED)
                    not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)
                if source_run.status == "success":
                    previous_successful_volumes.append(source_run.records_received)

        active_incidents = session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.pipeline_id.in_(pipeline_ids.values()),
                Incident.status.in_((IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED)),
            )
        )

    return CollectionReport(
        source_rows=len(source_runs),
        inserted_runs=inserted_runs,
        duplicate_runs=len(source_runs) - inserted_runs,
        unknown_dag_ids=snapshot.unknown_dag_ids,
        unknown_statuses=unknown_statuses,
        source_read_only=snapshot.source_read_only,
        inserted_checks=inserted_checks,
        failed_checks=failed_checks,
        not_measured_checks=not_measured_checks,
        active_incidents=active_incidents or 0,
    )


def count_mobility_runs(target_session_factory: sessionmaker[Session]) -> int:
    keys = [definition.pipeline_key for definition in PIPELINE_DEFINITIONS]
    with target_session_factory() as session:
        statement = (
            select(PipelineRun.id)
            .join(Pipeline, Pipeline.id == PipelineRun.pipeline_id)
            .where(Pipeline.pipeline_key.in_(keys))
        )
        return len(session.execute(statement).scalars().all())
