import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.mobility import collector as mobility_collector
from pfpd_ia.connectors.mobility.collector import (
    build_source_engine,
    collect_mobility_runs,
    count_mobility_runs,
)
from pfpd_ia.connectors.mobility.config import MobilitySettings, PipelineDefinition
from pfpd_ia.database import get_engine, get_session_factory
from pfpd_ia.models import Criticality

pytestmark = pytest.mark.integration


def _settings() -> MobilitySettings:
    return MobilitySettings(
        _env_file=None,
        mobility_database_url=get_settings().database_url,
        mobility_owner="data-engineering",
        mobility_environment="local",
        mobility_criticality=Criticality.MEDIUM,
        mobility_error_max_length=2000,
    )


def _prepare_source_fixture() -> None:
    now = datetime.now(UTC)
    with get_engine().begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS schema_analytics"))
        connection.execute(text("DROP TABLE IF EXISTS schema_analytics.fct_pipeline_runs"))
        connection.execute(
            text(
                """
                CREATE TABLE schema_analytics.fct_pipeline_runs (
                    pipeline_run_id text PRIMARY KEY,
                    dag_id text NOT NULL,
                    started_at timestamptz NOT NULL,
                    finished_at timestamptz NOT NULL,
                    status text NOT NULL,
                    records_received integer NOT NULL,
                    changed_record_count integer NOT NULL,
                    records_unchanged integer NOT NULL,
                    error_message text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO schema_analytics.fct_pipeline_runs VALUES
                ('velib::run-1', 'ingest_and_transform_velib', :start, :finish,
                 'success', 1516, 1500, 16, NULL),
                ('traffic::run-1', 'ingest_paris_road_traffic', :start, :finish,
                 'failed', 100, 90, 10,
                 'password=visible postgresql://reader:secret@database/mobility')
                """
            ),
            {"start": now, "finish": now + timedelta(minutes=2)},
        )


def _isolated_definitions(monkeypatch: pytest.MonkeyPatch) -> tuple[PipelineDefinition, ...]:
    suffix = uuid.uuid4().hex
    definitions = tuple(
        PipelineDefinition(
            dag_id=definition.dag_id,
            pipeline_key=f"test.{suffix}.{definition.pipeline_key}",
            display_name=definition.display_name,
            description=definition.description,
            expected_frequency_minutes=definition.expected_frequency_minutes,
        )
        for definition in mobility_collector.PIPELINE_DEFINITIONS
    )
    monkeypatch.setattr(mobility_collector, "PIPELINE_DEFINITIONS", definitions)
    return definitions


def _clean_fixture_and_target(definitions: tuple[PipelineDefinition, ...]) -> None:
    parameters = {
        "first_key": definitions[0].pipeline_key,
        "second_key": definitions[1].pipeline_key,
    }
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                DELETE FROM observability.incident_events
                WHERE incident_id IN (
                    SELECT i.id FROM observability.incidents i
                    JOIN observability.pipelines p ON p.id = i.pipeline_id
                    WHERE p.pipeline_key IN (:first_key, :second_key)
                )
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.incidents
                WHERE pipeline_id IN (
                    SELECT id FROM observability.pipelines
                    WHERE pipeline_key IN (:first_key, :second_key)
                )
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.quality_checks
                WHERE pipeline_id IN (
                    SELECT id FROM observability.pipelines
                    WHERE pipeline_key IN (:first_key, :second_key)
                )
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.data_assets
                WHERE pipeline_id IN (
                    SELECT id FROM observability.pipelines
                    WHERE pipeline_key IN (:first_key, :second_key)
                )
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.pipeline_runs
                WHERE pipeline_id IN (
                    SELECT id FROM observability.pipelines
                    WHERE pipeline_key IN (:first_key, :second_key)
                )
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.pipelines
                WHERE pipeline_key IN (:first_key, :second_key)
                """
            ),
            parameters,
        )
        connection.execute(text("DROP SCHEMA IF EXISTS schema_analytics CASCADE"))


def test_collection_is_read_only_sanitized_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = _isolated_definitions(monkeypatch)
    _clean_fixture_and_target(definitions)
    _prepare_source_fixture()
    settings = _settings()
    source_engine = build_source_engine(settings)
    try:
        evaluated_at = datetime.now(UTC) + timedelta(minutes=3)
        first = collect_mobility_runs(
            source_engine, get_session_factory(), settings, evaluated_at=evaluated_at
        )
        second = collect_mobility_runs(
            source_engine, get_session_factory(), settings, evaluated_at=evaluated_at
        )

        assert first.source_read_only is True
        assert first.source_rows == 2
        assert first.inserted_runs == 2
        assert first.duplicate_runs == 0
        assert first.unknown_statuses == ()
        assert first.inserted_checks == 10
        assert first.failed_checks == 0
        assert first.not_measured_checks == 3
        assert first.active_incidents == 0
        assert second.inserted_runs == 0
        assert second.duplicate_runs == 2
        assert second.inserted_checks == 0
        assert count_mobility_runs(get_session_factory()) == 2

        with get_engine().connect() as connection:
            stored_error = connection.execute(
                text(
                    """
                    SELECT r.error_message
                    FROM observability.pipeline_runs r
                    JOIN observability.pipelines p ON p.id = r.pipeline_id
                    WHERE r.external_run_id = 'traffic::run-1'
                      AND p.pipeline_key = :pipeline_key
                    """
                ),
                {"pipeline_key": definitions[1].pipeline_key},
            ).scalar_one()
        assert "visible" not in stored_error
        assert "secret" not in stored_error
    finally:
        source_engine.dispose()
        _clean_fixture_and_target(definitions)


def test_schema_break_is_recorded_without_querying_incompatible_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = _isolated_definitions(monkeypatch)
    _clean_fixture_and_target(definitions)
    _prepare_source_fixture()
    with get_engine().begin() as connection:
        connection.execute(
            text("ALTER TABLE schema_analytics.fct_pipeline_runs DROP COLUMN error_message")
        )

    settings = _settings()
    source_engine = build_source_engine(settings)
    try:
        report = collect_mobility_runs(
            source_engine,
            get_session_factory(),
            settings,
            evaluated_at=datetime.now(UTC),
        )

        assert report.source_rows == 0
        assert report.inserted_runs == 0
        assert report.failed_checks == 2
        assert report.not_measured_checks == 4
        assert report.active_incidents == 2
    finally:
        source_engine.dispose()
        _clean_fixture_and_target(definitions)


def test_source_engine_does_not_expose_secret_in_repr() -> None:
    source_engine = create_engine(
        "postgresql+psycopg://reader:secret-value@localhost:5432/mobility"
    )
    try:
        assert "secret-value" not in repr(source_engine.url)
    finally:
        source_engine.dispose()
