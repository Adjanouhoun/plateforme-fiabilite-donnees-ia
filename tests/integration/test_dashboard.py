import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pfpd_ia.dashboard.queries import (
    get_pipeline,
    get_portfolio_kpis,
    list_assets,
    list_checks,
    list_incidents,
    list_lineage,
    list_pipeline_summaries,
    list_runs,
)
from pfpd_ia.database import get_session_factory
from pfpd_ia.models import (
    CheckStatus,
    Criticality,
    DataAsset,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Pipeline,
    PipelineRun,
    QualityCheck,
    RunStatus,
    Severity,
)

pytestmark = pytest.mark.integration


def test_dashboard_queries_use_only_the_common_model() -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    pipeline_key = f"test.dashboard.{uuid.uuid4()}"

    with factory() as session, session.begin():
        pipeline = Pipeline(
            pipeline_key=pipeline_key,
            display_name="Pipeline tableau de bord",
            owner="test",
            environment="test",
            expected_frequency_minutes=60,
            criticality=Criticality.HIGH,
            is_active=True,
        )
        session.add(pipeline)
        session.flush()
        run = PipelineRun(
            pipeline_id=pipeline.id,
            external_run_id="run-1",
            started_at=now,
            ended_at=now,
            status=RunStatus.SUCCEEDED,
            rows_read=10,
            rows_written=10,
            rows_rejected=None,
            rows_unchanged=0,
        )
        asset = DataAsset(
            pipeline_id=pipeline.id,
            external_asset_id="runs",
            name="Exécutions",
            asset_type="view",
            source_system="test",
            logical_location="test.runs",
            schema_contract={},
            owner="test",
            sensitivity="internal",
            is_active=True,
        )
        session.add_all([run, asset])
        session.flush()
        check = QualityCheck(
            pipeline_id=pipeline.id,
            asset_id=asset.id,
            pipeline_run_id=run.id,
            idempotency_key="freshness:run-1",
            check_type="freshness",
            severity=Severity.ERROR,
            observed_value={"age_minutes": 361},
            expected_rule={"error_after_minutes": 360},
            status=CheckStatus.FAILED,
            checked_at=now,
            evidence_reference="test.runs",
        )
        session.add(check)
        session.flush()
        incident = Incident(
            pipeline_id=pipeline.id,
            triggering_check_id=check.id,
            deduplication_key=f"{asset.id}:freshness",
            title="Retard",
            severity=Severity.ERROR,
            status=IncidentStatus.OPEN,
            opened_at=now,
            business_impact=None,
            impact_origin="unknown",
        )
        session.add(incident)
        session.flush()
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                event_type="opened",
                occurred_at=now,
                actor="quality-engine",
                details={},
            )
        )
        session.flush()

        summary = next(
            item for item in list_pipeline_summaries(session) if item.pipeline_key == pipeline_key
        )
        assert summary.health_state == "incident_major"
        assert summary.active_incidents == 1
        assert summary.failed_checks == 1
        assert get_pipeline(session, pipeline_key)["display_name"] == "Pipeline tableau de bord"
        assert len(list_runs(session, pipeline_key)) == 1
        assert len(list_checks(session, pipeline_key)) == 1
        assert len(list_incidents(session, pipeline_key)) == 1
        assert len(list_assets(session, pipeline_key)) == 1
        assert list_lineage(session, pipeline_key) == []
        kpis = get_portfolio_kpis(
            session,
            pipeline_keys=[pipeline_key],
            window_days=7,
            evaluated_at=now + timedelta(seconds=1),
        )
        assert kpis.run_success_rate == 100.0
        assert kpis.check_conformity_rate == 0.0
        assert kpis.maximum_freshness_minutes == 361
        assert kpis.active_incidents_by_severity == {
            "critical": 0,
            "error": 1,
            "warning": 0,
            "info": 0,
        }
        assert kpis.average_closed_incident_minutes is None

        session.rollback()


def test_streamlit_app_renders_without_exception() -> None:
    app_path = Path(__file__).parents[2] / "src" / "pfpd_ia" / "dashboard" / "app.py"
    app = AppTest.from_file(app_path, default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "Fiabilité des données pour l’IA"
    navigation = next(radio for radio in app.radio if radio.label == "Vue")
    assert navigation.value == "Portefeuille"

    navigation.set_value("Détail d’un pipeline").run()
    assert not app.exception
