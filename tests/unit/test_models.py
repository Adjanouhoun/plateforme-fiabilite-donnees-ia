from pfpd_ia import models  # noqa: F401
from pfpd_ia.database import Base


def test_common_model_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "observability.data_assets",
        "observability.incident_events",
        "observability.incidents",
        "observability.lineage_edges",
        "observability.pipeline_runs",
        "observability.pipelines",
        "observability.quality_checks",
    }


def test_idempotency_constraints_exist() -> None:
    run_constraints = {
        constraint.name
        for constraint in Base.metadata.tables["observability.pipeline_runs"].constraints
    }
    check_constraints = {
        constraint.name
        for constraint in Base.metadata.tables["observability.quality_checks"].constraints
    }

    assert "uq_run_pipeline_external" in run_constraints
    assert "uq_check_pipeline_idempotency" in check_constraints


def test_active_incident_deduplication_index_exists() -> None:
    indexes = {index.name for index in Base.metadata.tables["observability.incidents"].indexes}

    assert "uq_incidents_active_deduplication" in indexes
