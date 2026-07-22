from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.mobility.collector import (
    build_source_engine,
    collect_mobility_runs,
    count_mobility_runs,
)
from pfpd_ia.connectors.mobility.config import MobilitySettings
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


def _clean_fixture_and_target() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                DELETE FROM observability.pipeline_runs
                WHERE pipeline_id IN (
                    SELECT id FROM observability.pipelines
                    WHERE pipeline_key IN ('mobility.velib', 'mobility.road_traffic')
                )
                """
            )
        )
        connection.execute(
            text(
                """
                DELETE FROM observability.pipelines
                WHERE pipeline_key IN ('mobility.velib', 'mobility.road_traffic')
                """
            )
        )
        connection.execute(text("DROP SCHEMA IF EXISTS schema_analytics CASCADE"))


def test_collection_is_read_only_sanitized_and_idempotent() -> None:
    _clean_fixture_and_target()
    _prepare_source_fixture()
    settings = _settings()
    source_engine = build_source_engine(settings)
    try:
        first = collect_mobility_runs(source_engine, get_session_factory(), settings)
        second = collect_mobility_runs(source_engine, get_session_factory(), settings)

        assert first.source_read_only is True
        assert first.source_rows == 2
        assert first.inserted_runs == 2
        assert first.duplicate_runs == 0
        assert first.unknown_statuses == ()
        assert second.inserted_runs == 0
        assert second.duplicate_runs == 2
        assert count_mobility_runs(get_session_factory()) == 2

        with get_engine().connect() as connection:
            stored_error = connection.execute(
                text(
                    """
                    SELECT error_message
                    FROM observability.pipeline_runs
                    WHERE external_run_id = 'traffic::run-1'
                    """
                )
            ).scalar_one()
        assert "visible" not in stored_error
        assert "secret" not in stored_error
    finally:
        source_engine.dispose()
        _clean_fixture_and_target()


def test_source_engine_does_not_expose_secret_in_repr() -> None:
    source_engine = create_engine(
        "postgresql+psycopg://reader:secret-value@localhost:5432/mobility"
    )
    try:
        assert "secret-value" not in repr(source_engine.url)
    finally:
        source_engine.dispose()
