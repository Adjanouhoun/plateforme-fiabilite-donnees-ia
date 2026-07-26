from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pfpd_ia.ai.contracts import (
    AssetFacts,
    CheckFacts,
    DownstreamAssetFacts,
    IncidentEventFacts,
    IncidentFactPackage,
    PipelineFacts,
)
from pfpd_ia.ai.sanitizer import sanitize_fact_package
from pfpd_ia.models import DataAsset, Incident, IncidentEvent, Pipeline, QualityCheck


class FactPackageUnavailable(ValueError):
    """Le modèle commun ne contient pas les faits minimaux requis."""


_DOWNSTREAM_ASSETS_QUERY = text(
    """
    WITH RECURSIVE downstream AS (
        SELECT
            edge.target_asset_id AS asset_id,
            1 AS distance,
            ARRAY[CAST(:triggering_asset_id AS uuid), edge.target_asset_id] AS visited
        FROM observability.lineage_edges edge
        WHERE edge.source_asset_id = :triggering_asset_id

        UNION ALL

        SELECT
            edge.target_asset_id,
            downstream.distance + 1,
            downstream.visited || edge.target_asset_id
        FROM downstream
        JOIN observability.lineage_edges edge
          ON edge.source_asset_id = downstream.asset_id
        WHERE NOT edge.target_asset_id = ANY(downstream.visited)
    ),
    nearest AS (
        SELECT asset_id, min(distance) AS distance
        FROM downstream
        GROUP BY asset_id
    )
    SELECT asset.id AS asset_id, asset.name, asset.asset_type, nearest.distance
    FROM nearest
    JOIN observability.data_assets asset ON asset.id = nearest.asset_id
    ORDER BY nearest.distance, asset.name, asset.id
    """
)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def build_incident_fact_package(session: Session, *, incident_id: uuid.UUID) -> IncidentFactPackage:
    """Construit et assainit les faits autorisés pour un incident enregistré."""

    row = session.execute(
        select(Incident, Pipeline, QualityCheck, DataAsset)
        .join(Pipeline, Pipeline.id == Incident.pipeline_id)
        .outerjoin(QualityCheck, QualityCheck.id == Incident.triggering_check_id)
        .outerjoin(DataAsset, DataAsset.id == QualityCheck.asset_id)
        .where(Incident.id == incident_id)
    ).one_or_none()
    if row is None:
        raise FactPackageUnavailable(f"Incident introuvable : {incident_id}")

    incident, pipeline, check, asset = row
    if check is None or asset is None:
        raise FactPackageUnavailable(
            f"Incident sans contrôle déclencheur exploitable : {incident_id}"
        )

    downstream_rows = session.execute(
        _DOWNSTREAM_ASSETS_QUERY,
        {"triggering_asset_id": asset.id},
    ).mappings()
    event_rows = session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident.id)
        .order_by(IncidentEvent.occurred_at, IncidentEvent.id)
    )

    package = IncidentFactPackage(
        incident_id=incident.id,
        status=_enum_value(incident.status),
        severity=_enum_value(incident.severity),
        opened_at=incident.opened_at,
        closed_at=incident.closed_at,
        impact_origin=_enum_value(incident.impact_origin),
        impact_documented=bool(incident.business_impact and incident.business_impact.strip()),
        pipeline=PipelineFacts(
            pipeline_key=pipeline.pipeline_key,
            environment=pipeline.environment,
            criticality=_enum_value(pipeline.criticality),
        ),
        triggering_asset=AssetFacts(
            asset_id=asset.id,
            name=asset.name,
            asset_type=asset.asset_type,
            source_system=asset.source_system,
            sensitivity=asset.sensitivity,
        ),
        triggering_check=CheckFacts(
            check_id=check.id,
            check_type=check.check_type,
            status=_enum_value(check.status),
            severity=_enum_value(check.severity),
            checked_at=check.checked_at,
            observed_value=check.observed_value,
            expected_rule=check.expected_rule,
            evidence_reference=check.evidence_reference,
        ),
        downstream_assets=[
            DownstreamAssetFacts(
                asset_id=row["asset_id"],
                name=row["name"],
                asset_type=row["asset_type"],
                distance=row["distance"],
            )
            for row in downstream_rows
        ],
        events=[
            IncidentEventFacts(event_type=event.event_type, occurred_at=event.occurred_at)
            for event in event_rows
        ],
    )
    return sanitize_fact_package(package)
