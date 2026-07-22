from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.connectors.mobility.config import (
    PIPELINE_DEFINITIONS,
    MobilitySettings,
    PipelineDefinition,
)
from pfpd_ia.connectors.mobility.sanitizer import sanitize_error_message
from pfpd_ia.models import Pipeline, PipelineRun, RunStatus

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


def _read_source_runs(
    source_engine: Engine,
) -> tuple[list[MobilityRunRecord], tuple[str, ...], bool]:
    allowed_dags = {definition.dag_id for definition in PIPELINE_DEFINITIONS}
    with source_engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        source_read_only = connection.execute(text("SHOW transaction_read_only")).scalar_one()
        if source_read_only != "on":
            raise RuntimeError("La transaction source Mobility n'est pas en lecture seule")

        observed_dags = set(connection.execute(SOURCE_DAGS_QUERY).scalars())
        unknown_dags = tuple(sorted(observed_dags - allowed_dags))
        parameters = {
            "velib_dag_id": PIPELINE_DEFINITIONS[0].dag_id,
            "traffic_dag_id": PIPELINE_DEFINITIONS[1].dag_id,
        }
        rows = connection.execute(SOURCE_RUNS_QUERY, parameters).mappings().all()

    return (
        [MobilityRunRecord.model_validate(row) for row in rows],
        unknown_dags,
        True,
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


def collect_mobility_runs(
    source_engine: Engine,
    target_session_factory: sessionmaker[Session],
    settings: MobilitySettings,
) -> CollectionReport:
    source_runs, unknown_dag_ids, source_read_only = _read_source_runs(source_engine)
    definitions_by_dag = {definition.dag_id: definition for definition in PIPELINE_DEFINITIONS}
    unknown_statuses = tuple(
        sorted({run.status for run in source_runs if run.status not in {"success", "failed"}})
    )

    inserted_runs = 0
    with target_session_factory.begin() as session:
        pipeline_ids = {
            definition.dag_id: _upsert_pipeline(session, definition, settings)
            for definition in PIPELINE_DEFINITIONS
        }

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
            if session.execute(statement).scalar_one_or_none() is not None:
                inserted_runs += 1

    return CollectionReport(
        source_rows=len(source_runs),
        inserted_runs=inserted_runs,
        duplicate_runs=len(source_runs) - inserted_runs,
        unknown_dag_ids=unknown_dag_ids,
        unknown_statuses=unknown_statuses,
        source_read_only=source_read_only,
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
