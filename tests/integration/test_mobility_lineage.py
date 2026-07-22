import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from pfpd_ia.connectors.mobility.config import PipelineDefinition
from pfpd_ia.connectors.mobility.lineage import DbtManifest, collect_manifest_lineage
from pfpd_ia.database import get_session_factory
from pfpd_ia.models import Criticality, DataAsset, LineageEdge, Pipeline

pytestmark = pytest.mark.integration


def test_manifest_lineage_is_scoped_duplicated_and_idempotent() -> None:
    suffix = uuid.uuid4().hex
    project = "dbt_mobility"
    shared_model_id = f"model.{project}.fct_pipeline_runs"
    source_ids = (f"source.{project}.raw.velib", f"source.{project}.raw.traffic")
    model_ids = (f"model.{project}.stg_velib", f"model.{project}.stg_traffic")
    definitions = tuple(
        PipelineDefinition(
            dag_id=f"dag-{index}",
            pipeline_key=f"test.lineage.{suffix}.{index}",
            display_name=f"Pipeline {index}",
            description="Test",
            expected_frequency_minutes=60,
            dbt_source_unique_ids=(source_ids[index],),
        )
        for index in range(2)
    )
    manifest = DbtManifest.model_validate(
        {
            "metadata": {
                "project_name": project,
                "dbt_version": "1.7.19",
                "generated_at": datetime.now(UTC),
            },
            "sources": {
                source_id: {
                    "unique_id": source_id,
                    "name": source_id.rsplit(".", 1)[-1],
                    "resource_type": "source",
                    "relation_name": source_id,
                }
                for source_id in source_ids
            },
            "nodes": {
                **{
                    model_ids[index]: {
                        "unique_id": model_ids[index],
                        "name": model_ids[index].rsplit(".", 1)[-1],
                        "resource_type": "model",
                        "relation_name": model_ids[index],
                        "depends_on": {"nodes": [source_ids[index]]},
                    }
                    for index in range(2)
                },
                shared_model_id: {
                    "unique_id": shared_model_id,
                    "name": "fct_pipeline_runs",
                    "resource_type": "model",
                    "relation_name": "schema_analytics.fct_pipeline_runs",
                    "depends_on": {"nodes": list(model_ids)},
                },
            },
        }
    )
    factory = get_session_factory()
    with factory.begin() as session:
        for definition in definitions:
            pipeline = Pipeline(
                pipeline_key=definition.pipeline_key,
                display_name=definition.display_name,
                owner="test",
                environment="test",
                expected_frequency_minutes=60,
                criticality=Criticality.MEDIUM,
                is_active=True,
            )
            session.add(pipeline)
            session.flush()
            session.add(
                DataAsset(
                    pipeline_id=pipeline.id,
                    external_asset_id=definition.asset_external_id,
                    name="Exécutions",
                    asset_type="view",
                    source_system="test",
                    logical_location=definition.asset_logical_location,
                    schema_contract={"dbt_unique_id": shared_model_id},
                    owner="test",
                    sensitivity="internal",
                    is_active=True,
                )
            )

    try:
        first = collect_manifest_lineage(
            manifest=manifest,
            target_session_factory=factory,
            definitions=definitions,
        )
        second = collect_manifest_lineage(
            manifest=manifest,
            target_session_factory=factory,
            definitions=definitions,
        )
        assert first.assets_observed == second.assets_observed == 6
        assert first.edges_observed == second.edges_observed == 4
        with factory() as session:
            pipeline_ids = select(Pipeline.id).where(
                Pipeline.pipeline_key.in_([item.pipeline_key for item in definitions])
            )
            asset_ids = select(DataAsset.id).where(DataAsset.pipeline_id.in_(pipeline_ids))
            assert (
                session.scalar(
                    select(func.count()).select_from(DataAsset).where(DataAsset.id.in_(asset_ids))
                )
                == 6
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(LineageEdge)
                    .where(LineageEdge.source_asset_id.in_(asset_ids))
                )
                == 4
            )
    finally:
        with factory.begin() as session:
            pipeline_ids = select(Pipeline.id).where(
                Pipeline.pipeline_key.in_([item.pipeline_key for item in definitions])
            )
            asset_ids = select(DataAsset.id).where(DataAsset.pipeline_id.in_(pipeline_ids))
            session.execute(
                delete(LineageEdge).where(
                    LineageEdge.source_asset_id.in_(asset_ids)
                    | LineageEdge.target_asset_id.in_(asset_ids)
                )
            )
            session.execute(delete(DataAsset).where(DataAsset.pipeline_id.in_(pipeline_ids)))
            session.execute(delete(Pipeline).where(Pipeline.id.in_(pipeline_ids)))
