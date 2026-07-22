from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pfpd_ia.connectors.mobility.config import PipelineDefinition
from pfpd_ia.models import DataAsset, LineageEdge, Pipeline


class ManifestMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: str
    dbt_version: str
    generated_at: datetime


class ManifestDependsOn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: list[str] = Field(default_factory=list)


class ManifestNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    unique_id: str
    name: str
    resource_type: Literal["model", "source"]
    database: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    alias: str | None = None
    relation_name: str | None = None
    depends_on: ManifestDependsOn = Field(default_factory=ManifestDependsOn)

    @property
    def logical_location(self) -> str:
        if self.relation_name:
            return self.relation_name.replace('"', "")
        parts = (self.database, self.schema_name, self.alias or self.name)
        return ".".join(part for part in parts if part)


class DbtManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metadata: ManifestMetadata
    nodes: dict[str, ManifestNode]
    sources: dict[str, ManifestNode]

    @property
    def lineage_nodes(self) -> dict[str, ManifestNode]:
        return {**self.sources, **self.nodes}


@dataclass(frozen=True)
class LineageCollectionReport:
    project_name: str
    generated_at: datetime
    pipelines: int
    assets_observed: int
    edges_observed: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_manifest(path: Path, *, expected_project_name: str) -> DbtManifest:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("La racine du manifest dbt doit être un objet")
        payload["nodes"] = {
            key: value
            for key, value in payload.get("nodes", {}).items()
            if value.get("resource_type") == "model"
        }
        payload["sources"] = {
            key: value
            for key, value in payload.get("sources", {}).items()
            if value.get("resource_type") == "source"
        }
        manifest = DbtManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError, AttributeError) as error:
        raise ValueError(f"Manifest dbt invalide ou illisible: {type(error).__name__}") from error
    if manifest.metadata.project_name != expected_project_name:
        raise ValueError("Le projet du manifest dbt ne correspond pas au projet attendu")
    for unique_id, node in manifest.lineage_nodes.items():
        if unique_id != node.unique_id:
            raise ValueError("Le manifest dbt contient un identifiant de nœud incohérent")
    return manifest


def _reachable_nodes(
    nodes: dict[str, ManifestNode], source_unique_ids: tuple[str, ...]
) -> set[str]:
    missing = sorted(set(source_unique_ids) - nodes.keys())
    if missing:
        raise ValueError(f"Sources dbt attendues absentes du manifest: {', '.join(missing)}")
    reachable = set(source_unique_ids)
    changed = True
    while changed:
        changed = False
        for node in nodes.values():
            if node.unique_id in reachable:
                continue
            if any(parent in reachable for parent in node.depends_on.nodes):
                reachable.add(node.unique_id)
                changed = True
    return reachable


def _asset_external_id(node: ManifestNode, definition: PipelineDefinition) -> str:
    if node.unique_id == definition.monitoring_asset_dbt_unique_id:
        return definition.asset_external_id
    return node.unique_id


def _upsert_asset(
    session: Session,
    *,
    pipeline: Pipeline,
    definition: PipelineDefinition,
    node: ManifestNode,
) -> Any:
    external_id = _asset_external_id(node, definition)
    if node.unique_id == definition.monitoring_asset_dbt_unique_id:
        existing_id = session.scalar(
            select(DataAsset.id).where(
                DataAsset.pipeline_id == pipeline.id,
                DataAsset.external_asset_id == external_id,
            )
        )
        if existing_id is None:
            raise ValueError(
                f"Actif de monitoring absent pour le pipeline {definition.pipeline_key}"
            )
        return existing_id
    schema_contract = {"dbt_unique_id": node.unique_id, "proof_type": "dbt_manifest"}
    statement = (
        insert(DataAsset)
        .values(
            pipeline_id=pipeline.id,
            external_asset_id=external_id,
            name=node.name,
            asset_type=f"dbt_{node.resource_type}",
            source_system="dbt",
            logical_location=node.logical_location,
            schema_contract=schema_contract,
            owner=pipeline.owner,
            sensitivity="internal",
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[DataAsset.pipeline_id, DataAsset.external_asset_id],
            set_={
                "name": node.name,
                "asset_type": f"dbt_{node.resource_type}",
                "source_system": "dbt",
                "logical_location": node.logical_location,
                "schema_contract": schema_contract,
                "owner": pipeline.owner,
                "is_active": True,
            },
        )
        .returning(DataAsset.id)
    )
    return session.execute(statement).scalar_one()


def collect_manifest_lineage(
    *,
    manifest: DbtManifest,
    target_session_factory: sessionmaker[Session],
    definitions: tuple[PipelineDefinition, ...],
) -> LineageCollectionReport:
    nodes = manifest.lineage_nodes
    asset_count = 0
    edge_count = 0
    with target_session_factory.begin() as session:
        pipelines = {
            pipeline.pipeline_key: pipeline
            for pipeline in session.scalars(
                select(Pipeline).where(
                    Pipeline.pipeline_key.in_([item.pipeline_key for item in definitions])
                )
            )
        }
        missing_pipelines = sorted(
            definition.pipeline_key
            for definition in definitions
            if definition.pipeline_key not in pipelines
        )
        if missing_pipelines:
            raise ValueError(
                "Pipelines Mobility absents du modèle commun: " + ", ".join(missing_pipelines)
            )

        for definition in definitions:
            pipeline = pipelines[definition.pipeline_key]
            reachable = _reachable_nodes(nodes, definition.dbt_source_unique_ids)
            asset_ids = {
                unique_id: _upsert_asset(
                    session,
                    pipeline=pipeline,
                    definition=definition,
                    node=nodes[unique_id],
                )
                for unique_id in sorted(reachable)
            }
            asset_count += len(asset_ids)
            for target_unique_id in sorted(reachable):
                target = nodes[target_unique_id]
                for source_unique_id in sorted(target.depends_on.nodes):
                    if source_unique_id not in reachable:
                        continue
                    evidence = (
                        f"dbt_manifest:{manifest.metadata.project_name}:"
                        f"{source_unique_id}->{target_unique_id}"
                    )
                    statement = (
                        insert(LineageEdge)
                        .values(
                            source_asset_id=asset_ids[source_unique_id],
                            target_asset_id=asset_ids[target_unique_id],
                            transformation_type="dbt_dependency",
                            evidence_origin=evidence,
                            observed_at=manifest.metadata.generated_at,
                        )
                        .on_conflict_do_update(
                            constraint="uq_lineage_evidence",
                            set_={"observed_at": manifest.metadata.generated_at},
                        )
                    )
                    session.execute(statement)
                    edge_count += 1

    return LineageCollectionReport(
        project_name=manifest.metadata.project_name,
        generated_at=manifest.metadata.generated_at,
        pipelines=len(definitions),
        assets_observed=asset_count,
        edges_observed=edge_count,
    )
