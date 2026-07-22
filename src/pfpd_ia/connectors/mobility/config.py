from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pfpd_ia.models import Criticality


class MobilitySettings(BaseSettings):
    """Configuration explicite et non affichable du connecteur Mobility."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mobility_database_url: SecretStr
    mobility_owner: str = Field(min_length=1)
    mobility_environment: Literal["local", "production"]
    mobility_criticality: Criticality
    mobility_error_max_length: int = Field(default=2000, ge=256, le=10_000)


class MobilityLineageSettings(BaseSettings):
    """Contrat explicite de l'artefact dbt utilisé comme preuve structurelle."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mobility_dbt_manifest_path: Path
    mobility_dbt_project_name: str = Field(default="dbt_mobility", min_length=1)


@dataclass(frozen=True)
class PipelineDefinition:
    dag_id: str
    pipeline_key: str
    display_name: str
    description: str
    expected_frequency_minutes: int
    dbt_source_unique_ids: tuple[str, ...]

    @property
    def asset_external_id(self) -> str:
        return "pipeline-runs"

    @property
    def asset_logical_location(self) -> str:
        return f"schema_analytics.fct_pipeline_runs?dag_id={self.dag_id}"

    @property
    def monitoring_asset_dbt_unique_id(self) -> str:
        return "model.dbt_mobility.fct_pipeline_runs"


PIPELINE_DEFINITIONS = (
    PipelineDefinition(
        dag_id="ingest_and_transform_velib",
        pipeline_key="mobility.velib",
        display_name="Vélib",
        description="Ingestion horaire des disponibilités Vélib parisiennes.",
        expected_frequency_minutes=60,
        dbt_source_unique_ids=(
            "source.dbt_mobility.raw_data.stg_raw_stations",
            "source.dbt_mobility.monitoring_data.ingestion_runs",
        ),
    ),
    PipelineDefinition(
        dag_id="ingest_paris_road_traffic",
        pipeline_key="mobility.road_traffic",
        display_name="Trafic routier",
        description="Ingestion horaire des comptages routiers permanents parisiens.",
        expected_frequency_minutes=60,
        dbt_source_unique_ids=(
            "source.dbt_mobility.road_traffic_raw.road_traffic_observations",
            "source.dbt_mobility.monitoring_data.traffic_ingestion_runs",
        ),
    ),
)

EXPECTED_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "pipeline_run_id": ("text", "character varying"),
    "dag_id": ("text", "character varying"),
    "started_at": ("timestamp with time zone",),
    "finished_at": ("timestamp with time zone",),
    "status": ("text", "character varying"),
    "records_received": ("smallint", "integer", "bigint", "numeric"),
    "changed_record_count": ("smallint", "integer", "bigint", "numeric"),
    "records_unchanged": ("smallint", "integer", "bigint", "numeric"),
    "error_message": ("text", "character varying"),
}
