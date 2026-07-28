import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.employment import collector as employment_collector
from pfpd_ia.connectors.employment.collector import (
    build_source_engine,
    collect_employment_runs,
    count_employment_runs,
)
from pfpd_ia.connectors.employment.config import EmploymentPipelineDefinition, EmploymentSettings
from pfpd_ia.database import get_engine, get_session_factory
from pfpd_ia.models import Criticality

pytestmark = pytest.mark.integration


def _settings() -> EmploymentSettings:
    return EmploymentSettings(
        _env_file=None,
        employment_database_url=get_settings().database_url,
        employment_owner="data-engineering",
        employment_environment="local",
        employment_criticality=Criticality.MEDIUM,
        employment_error_max_length=2000,
    )


def _definitions(monkeypatch: pytest.MonkeyPatch) -> tuple[EmploymentPipelineDefinition, ...]:
    suffix = uuid.uuid4().hex
    definitions = tuple(
        EmploymentPipelineDefinition(
            provider=definition.provider,
            pipeline_key=f"test.{suffix}.{definition.pipeline_key}",
            display_name=definition.display_name,
            description=definition.description,
            expected_frequency_minutes=definition.expected_frequency_minutes,
        )
        for definition in employment_collector.PIPELINE_DEFINITIONS
    )
    monkeypatch.setattr(employment_collector, "PIPELINE_DEFINITIONS", definitions)
    return definitions


def _clean(definitions: tuple[EmploymentPipelineDefinition, ...]) -> None:
    keys = [definition.pipeline_key for definition in definitions]
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "DELETE FROM observability.incident_events WHERE incident_id IN "
                "(SELECT i.id FROM observability.incidents i JOIN observability.pipelines p "
                "ON p.id = i.pipeline_id WHERE p.pipeline_key = ANY(:keys))"
            ),
            {"keys": keys},
        )
        for table in ("incidents", "quality_checks", "data_assets", "pipeline_runs", "pipelines"):
            connection.execute(
                text(
                    f"DELETE FROM observability.{table} WHERE "
                    + (
                        "pipeline_id IN (SELECT id FROM observability.pipelines WHERE pipeline_key = ANY(:keys))"
                        if table != "pipelines"
                        else "pipeline_key = ANY(:keys)"
                    )
                ),
                {"keys": keys},
            )
        connection.execute(text("DROP SCHEMA IF EXISTS app CASCADE"))


def _source_fixture() -> None:
    now = datetime.now(UTC)
    with get_engine().begin() as connection:
        connection.execute(text("CREATE SCHEMA app"))
        connection.execute(
            text(
                "CREATE TABLE app.sync_runs (id text PRIMARY KEY, provider text NOT NULL, status text NOT NULL, "
                "started_at timestamptz NOT NULL, completed_at timestamptz, offers_seen integer NOT NULL, "
                "segments_expected integer NOT NULL, segments_completed integer NOT NULL, error_summary text)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO app.sync_runs VALUES "
                "('ft::1', 'france_travail', 'success', :start, :end, 100, 4, 4, NULL), "
                "('lba::1', 'la_bonne_alternance', 'failed', :start, :end, 0, 3, 2, 'password=visible')"
            ),
            {"start": now, "end": now + timedelta(minutes=2)},
        )


def test_collects_metadata_read_only_and_keeps_dashboard_model_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = _definitions(monkeypatch)
    _clean(definitions)
    _source_fixture()
    source_engine = build_source_engine(_settings())
    try:
        report = collect_employment_runs(
            source_engine,
            get_session_factory(),
            _settings(),
            evaluated_at=datetime.now(UTC) + timedelta(minutes=3),
        )
        duplicate = collect_employment_runs(
            source_engine,
            get_session_factory(),
            _settings(),
            evaluated_at=datetime.now(UTC) + timedelta(minutes=3),
        )
        assert report.source_read_only is True
        assert report.source_rows == 2
        assert report.inserted_runs == 2
        assert report.failed_checks == 1
        assert duplicate.duplicate_runs == 2
        assert count_employment_runs(get_session_factory()) == 2
        with get_engine().connect() as connection:
            error = connection.execute(
                text(
                    "SELECT error_message FROM observability.pipeline_runs WHERE external_run_id = 'lba::1'"
                )
            ).scalar_one()
        assert "visible" not in error
    finally:
        source_engine.dispose()
        _clean(definitions)
