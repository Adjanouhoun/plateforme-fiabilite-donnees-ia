import json
from pathlib import Path

import pytest

from pfpd_ia.connectors.mobility.lineage import load_manifest


def _manifest_payload() -> dict[str, object]:
    source_id = "source.dbt_mobility.raw_data.input"
    model_id = "model.dbt_mobility.stg_input"
    return {
        "metadata": {
            "project_name": "dbt_mobility",
            "dbt_version": "1.7.19",
            "generated_at": "2026-07-19T00:00:09Z",
        },
        "sources": {
            source_id: {
                "unique_id": source_id,
                "name": "input",
                "resource_type": "source",
                "database": "warehouse",
                "schema": "raw",
                "alias": "input",
                "relation_name": '"warehouse"."raw"."input"',
                "depends_on": {"nodes": []},
            }
        },
        "nodes": {
            model_id: {
                "unique_id": model_id,
                "name": "stg_input",
                "resource_type": "model",
                "database": "warehouse",
                "schema": "analytics",
                "alias": "stg_input",
                "relation_name": '"warehouse"."analytics"."stg_input"',
                "depends_on": {"nodes": [source_id]},
            }
        },
    }


def test_manifest_is_validated_and_keeps_structural_proof(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    manifest = load_manifest(path, expected_project_name="dbt_mobility")

    assert manifest.metadata.project_name == "dbt_mobility"
    assert len(manifest.lineage_nodes) == 2
    assert manifest.nodes["model.dbt_mobility.stg_input"].logical_location == (
        "warehouse.analytics.stg_input"
    )


def test_manifest_rejects_an_unexpected_project(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    with pytest.raises(ValueError, match="projet attendu"):
        load_manifest(path, expected_project_name="another_project")


def test_manifest_rejects_an_inconsistent_node_identifier(tmp_path: Path) -> None:
    payload = _manifest_payload()
    payload["nodes"]["model.dbt_mobility.stg_input"]["unique_id"] = "model.other.invalid"  # type: ignore[index]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identifiant de nœud incohérent"):
        load_manifest(path, expected_project_name="dbt_mobility")
