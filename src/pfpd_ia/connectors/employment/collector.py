from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.connectors.employment.config import (
    EXPECTED_SOURCE_COLUMNS,
    PIPELINE_DEFINITIONS,
    EmploymentPipelineDefinition,
    EmploymentSettings,
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
    evaluate_completeness,
    evaluate_freshness,
    evaluate_schema,
    evaluate_uniqueness,
    evaluate_volume,
)

SOURCE_SCHEMA_QUERY = text("""
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'app' AND table_name = 'sync_runs' ORDER BY ordinal_position
""")
SOURCE_PROVIDERS_QUERY = text("SELECT DISTINCT provider FROM app.sync_runs ORDER BY provider")
SOURCE_RUNS_QUERY = text("""
SELECT id, provider, status, started_at, completed_at, offers_seen,
       segments_expected, segments_completed, error_summary
FROM app.sync_runs
WHERE provider IN (:france_travail_provider, :lba_provider)
ORDER BY started_at, id
""")
SOURCE_UNIQUENESS_QUERY = text("""
SELECT provider, count(*) AS total_count, count(DISTINCT id) AS distinct_count
FROM app.sync_runs
WHERE provider IN (:france_travail_provider, :lba_provider)
GROUP BY provider
""")


class EmploymentRunRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    offers_seen: int
    segments_expected: int
    segments_completed: int
    error_summary: str | None


@dataclass(frozen=True)
class EmploymentCollectionReport:
    source_rows: int
    inserted_runs: int
    duplicate_runs: int
    unknown_providers: tuple[str, ...]
    unknown_statuses: tuple[str, ...]
    source_read_only: bool
    inserted_checks: int
    failed_checks: int
    not_measured_checks: int
    active_incidents: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSnapshot:
    runs: tuple[EmploymentRunRecord, ...]
    unknown_providers: tuple[str, ...]
    source_read_only: bool
    actual_columns: dict[str, str]
    uniqueness_by_provider: dict[str, tuple[int, int]]


def build_source_engine(settings: EmploymentSettings) -> Engine:
    return create_engine(
        settings.employment_database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"application_name": "pfpd_ia_employment_reader", "connect_timeout": 10},
    )


def _parameters() -> dict[str, str]:
    return {
        "france_travail_provider": PIPELINE_DEFINITIONS[0].provider,
        "lba_provider": PIPELINE_DEFINITIONS[1].provider,
    }


def _read_source_runs(source_engine: Engine) -> SourceSnapshot:
    allowed = {definition.provider for definition in PIPELINE_DEFINITIONS}
    with source_engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        if connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
            raise RuntimeError("La transaction source Emploi n'est pas en lecture seule")
        actual_columns = dict(connection.execute(SOURCE_SCHEMA_QUERY).all())
        if (
            evaluate_schema(
                actual_columns=actual_columns, expected_columns=EXPECTED_SOURCE_COLUMNS
            ).status
            == CheckStatus.FAILED
        ):
            return SourceSnapshot((), (), True, actual_columns, {})
        observed_providers = set(connection.execute(SOURCE_PROVIDERS_QUERY).scalars())
        parameters = _parameters()
        rows = connection.execute(SOURCE_RUNS_QUERY, parameters).mappings().all()
        uniqueness = {
            row.provider: (row.total_count, row.distinct_count)
            for row in connection.execute(SOURCE_UNIQUENESS_QUERY, parameters)
        }
    return SourceSnapshot(
        runs=tuple(EmploymentRunRecord.model_validate(row) for row in rows),
        unknown_providers=tuple(sorted(observed_providers - allowed)),
        source_read_only=True,
        actual_columns=actual_columns,
        uniqueness_by_provider=uniqueness,
    )


def _upsert_pipeline(
    session: Session, definition: EmploymentPipelineDefinition, settings: EmploymentSettings
):
    return session.execute(
        insert(Pipeline)
        .values(
            pipeline_key=definition.pipeline_key,
            display_name=definition.display_name,
            description=definition.description,
            owner=settings.employment_owner,
            environment=settings.employment_environment,
            expected_frequency_minutes=definition.expected_frequency_minutes,
            criticality=settings.employment_criticality,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Pipeline.pipeline_key],
            set_={
                "display_name": definition.display_name,
                "description": definition.description,
                "owner": settings.employment_owner,
                "environment": settings.employment_environment,
                "expected_frequency_minutes": definition.expected_frequency_minutes,
                "criticality": settings.employment_criticality,
                "is_active": True,
            },
        )
        .returning(Pipeline.id)
    ).scalar_one()


def _upsert_asset(
    session: Session,
    pipeline_id,
    definition: EmploymentPipelineDefinition,
    settings: EmploymentSettings,
):
    contract = {
        "columns": {column: list(types) for column, types in EXPECTED_SOURCE_COLUMNS.items()},
        "filter": {"provider": definition.provider},
        "scope": "sync_run_metadata_only",
    }
    return session.execute(
        insert(DataAsset)
        .values(
            pipeline_id=pipeline_id,
            external_asset_id=definition.asset_external_id,
            name=f"Synchronisations {definition.display_name}",
            asset_type="table",
            source_system="assistant_candidature_emploi",
            logical_location=definition.asset_logical_location,
            schema_contract=contract,
            owner=settings.employment_owner,
            sensitivity="internal",
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[DataAsset.pipeline_id, DataAsset.external_asset_id],
            set_={
                "name": f"Synchronisations {definition.display_name}",
                "asset_type": "table",
                "source_system": "assistant_candidature_emploi",
                "logical_location": definition.asset_logical_location,
                "schema_contract": contract,
                "owner": settings.employment_owner,
                "sensitivity": "internal",
                "is_active": True,
            },
        )
        .returning(DataAsset.id)
    ).scalar_one()


def _status(value: str) -> RunStatus:
    return {
        "success": RunStatus.SUCCEEDED,
        "succeeded": RunStatus.SUCCEEDED,
        "failed": RunStatus.FAILED,
        "running": RunStatus.RUNNING,
    }.get(value, RunStatus.UNKNOWN)


def _record(
    session: Session,
    *,
    pipeline_id,
    asset_id,
    run_id,
    key: str,
    evaluation: CheckEvaluation,
    checked_at: datetime,
    definition: EmploymentPipelineDefinition,
) -> tuple[bool, CheckStatus]:
    _, _, inserted = record_check_and_reconcile_incident(
        session,
        pipeline_id=pipeline_id,
        asset_id=asset_id,
        pipeline_run_id=run_id,
        idempotency_key=key,
        evaluation=replace(evaluation, evidence_reference=definition.asset_logical_location),
        checked_at=checked_at,
        incident_title=f"{definition.display_name} — contrôle {evaluation.check_type} en échec",
    )
    return inserted, evaluation.status


def collect_employment_runs(
    source_engine: Engine,
    target_session_factory: sessionmaker[Session],
    settings: EmploymentSettings,
    evaluated_at: datetime | None = None,
) -> EmploymentCollectionReport:
    snapshot = _read_source_runs(source_engine)
    evaluated_at = evaluated_at or datetime.now(UTC)
    slot = evaluated_at.replace(minute=0, second=0, microsecond=0).isoformat()
    definitions = {definition.provider: definition for definition in PIPELINE_DEFINITIONS}
    runs = snapshot.runs
    unknown_statuses = tuple(
        sorted(
            {
                run.status
                for run in runs
                if run.status not in {"success", "succeeded", "failed", "running"}
            }
        )
    )
    inserted_runs = inserted_checks = failed_checks = not_measured_checks = 0
    with target_session_factory.begin() as session:
        pipeline_ids = {
            definition.provider: _upsert_pipeline(session, definition, settings)
            for definition in PIPELINE_DEFINITIONS
        }
        asset_ids = {
            definition.provider: _upsert_asset(
                session, pipeline_ids[definition.provider], definition, settings
            )
            for definition in PIPELINE_DEFINITIONS
        }
        for definition in PIPELINE_DEFINITIONS:
            evaluations = [
                (
                    f"schema:{slot}",
                    evaluate_schema(
                        actual_columns=snapshot.actual_columns,
                        expected_columns=EXPECTED_SOURCE_COLUMNS,
                    ),
                ),
                (
                    f"uniqueness:{slot}",
                    evaluate_uniqueness(
                        total_count=(
                            snapshot.uniqueness_by_provider.get(definition.provider) or (None, None)
                        )[0],
                        distinct_count=(
                            snapshot.uniqueness_by_provider.get(definition.provider) or (None, None)
                        )[1],
                    ),
                ),
            ]
            for key, evaluation in evaluations:
                inserted, status = _record(
                    session,
                    pipeline_id=pipeline_ids[definition.provider],
                    asset_id=asset_ids[definition.provider],
                    run_id=None,
                    key=key,
                    evaluation=evaluation,
                    checked_at=evaluated_at,
                    definition=definition,
                )
                inserted_checks += int(inserted)
                failed_checks += int(inserted and status == CheckStatus.FAILED)
                not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)
        run_ids: dict[tuple[str, str], object] = {}
        for run in runs:
            definition = definitions[run.provider]
            statement = (
                insert(PipelineRun)
                .values(
                    pipeline_id=pipeline_ids[run.provider],
                    external_run_id=run.id,
                    started_at=run.started_at,
                    ended_at=run.completed_at,
                    status=_status(run.status),
                    rows_read=run.offers_seen,
                    rows_written=None,
                    rows_rejected=None,
                    rows_unchanged=None,
                    error_message=sanitize_error_message(
                        run.error_summary, settings.employment_error_max_length
                    ),
                )
                .on_conflict_do_nothing(
                    index_elements=[PipelineRun.pipeline_id, PipelineRun.external_run_id]
                )
                .returning(PipelineRun.id)
            )
            target_id = session.execute(statement).scalar_one_or_none()
            if target_id is None:
                session.execute(
                    update(PipelineRun)
                    .where(
                        PipelineRun.pipeline_id == pipeline_ids[run.provider],
                        PipelineRun.external_run_id == run.id,
                    )
                    .values(
                        ended_at=run.completed_at,
                        status=_status(run.status),
                        rows_read=run.offers_seen,
                        error_message=sanitize_error_message(
                            run.error_summary, settings.employment_error_max_length
                        ),
                    )
                )
                target_id = session.execute(
                    select(PipelineRun.id).where(
                        PipelineRun.pipeline_id == pipeline_ids[run.provider],
                        PipelineRun.external_run_id == run.id,
                    )
                ).scalar_one()
            else:
                inserted_runs += 1
            run_ids[(run.provider, run.id)] = target_id
        for definition in PIPELINE_DEFINITIONS:
            scoped = [run for run in runs if run.provider == definition.provider]
            successful = [
                run
                for run in scoped
                if run.status in {"success", "succeeded"} and run.completed_at is not None
            ]
            fresh = evaluate_freshness(
                latest_success_at=max((run.completed_at for run in successful), default=None),
                evaluated_at=evaluated_at,
                warning_after_minutes=definition.expected_frequency_minutes * 2,
                error_after_minutes=definition.expected_frequency_minutes * 3,
            )
            inserted, status = _record(
                session,
                pipeline_id=pipeline_ids[definition.provider],
                asset_id=asset_ids[definition.provider],
                run_id=None,
                key=f"freshness:{slot}",
                evaluation=fresh,
                checked_at=evaluated_at,
                definition=definition,
            )
            inserted_checks += int(inserted)
            failed_checks += int(inserted and status == CheckStatus.FAILED)
            not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)
            references: list[int] = []
            for run in sorted(scoped, key=lambda item: (item.started_at, item.id)):
                evaluations = [
                    evaluate_completeness(
                        expected_count=run.segments_expected, completed_count=run.segments_completed
                    ),
                    evaluate_volume(
                        current_volume=run.offers_seen if run.status == "success" else None,
                        reference_volumes=list(reversed(references[-5:])),
                    ),
                ]
                for evaluation in evaluations:
                    inserted, status = _record(
                        session,
                        pipeline_id=pipeline_ids[definition.provider],
                        asset_id=asset_ids[definition.provider],
                        run_id=run_ids[(run.provider, run.id)],
                        key=f"{evaluation.check_type}:{run.id}",
                        evaluation=evaluation,
                        checked_at=run.completed_at or run.started_at,
                        definition=definition,
                    )
                    inserted_checks += int(inserted)
                    failed_checks += int(inserted and status == CheckStatus.FAILED)
                    not_measured_checks += int(inserted and status == CheckStatus.NOT_MEASURED)
                if run.status in {"success", "succeeded"}:
                    references.append(run.offers_seen)
        active = session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.pipeline_id.in_(pipeline_ids.values()),
                Incident.status.in_((IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED)),
            )
        )
    return EmploymentCollectionReport(
        len(runs),
        inserted_runs,
        len(runs) - inserted_runs,
        snapshot.unknown_providers,
        unknown_statuses,
        snapshot.source_read_only,
        inserted_checks,
        failed_checks,
        not_measured_checks,
        active or 0,
    )


def count_employment_runs(target_session_factory: sessionmaker[Session]) -> int:
    keys = [definition.pipeline_key for definition in PIPELINE_DEFINITIONS]
    with target_session_factory() as session:
        return len(
            session.execute(
                select(PipelineRun.id).join(Pipeline).where(Pipeline.pipeline_key.in_(keys))
            )
            .scalars()
            .all()
        )
