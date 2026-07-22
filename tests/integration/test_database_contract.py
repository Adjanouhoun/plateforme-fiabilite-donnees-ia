import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from pfpd_ia.database import get_engine
from pfpd_ia.main import app

pytestmark = pytest.mark.integration


def test_migration_creates_expected_tables() -> None:
    inspector = inspect(get_engine())

    assert set(inspector.get_table_names(schema="observability")) == {
        "data_assets",
        "incident_events",
        "incidents",
        "lineage_edges",
        "pipeline_runs",
        "pipelines",
        "quality_checks",
    }
    assert "alembic_version" in inspector.get_table_names(schema="public")


def test_database_is_ready() -> None:
    with get_engine().connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_readiness_requires_database_and_schema() -> None:
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "available"}


def test_pipeline_key_is_unique() -> None:
    pipeline_id = uuid.uuid4()
    statement = text(
        """
        INSERT INTO observability.pipelines (
            id, pipeline_key, display_name, owner, environment,
            expected_frequency_minutes, criticality, is_active
        ) VALUES (
            :id, 'duplicate-key', 'Pipeline test', 'test', 'test', 60, 'low', true
        )
        """
    )

    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(statement, {"id": pipeline_id})
            with pytest.raises(IntegrityError):
                connection.execute(statement, {"id": uuid.uuid4()})
        finally:
            transaction.rollback()


def test_negative_run_volume_is_rejected() -> None:
    pipeline_id = uuid.uuid4()
    now = datetime.now(UTC)

    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO observability.pipelines (
                        id, pipeline_key, display_name, owner, environment,
                        expected_frequency_minutes, criticality, is_active
                    ) VALUES (
                        :id, :key, 'Pipeline test', 'test', 'test', 60, 'low', true
                    )
                    """
                ),
                {"id": pipeline_id, "key": f"pipeline-{pipeline_id}"},
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO observability.pipeline_runs (
                            id, pipeline_id, external_run_id, started_at,
                            status, rows_read
                        ) VALUES (
                            :id, :pipeline_id, 'run-1', :started_at,
                            'failed', -1
                        )
                        """
                    ),
                    {"id": uuid.uuid4(), "pipeline_id": pipeline_id, "started_at": now},
                )
        finally:
            transaction.rollback()
