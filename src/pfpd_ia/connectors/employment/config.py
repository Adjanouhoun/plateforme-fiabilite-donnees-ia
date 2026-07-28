from dataclasses import dataclass
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pfpd_ia.models import Criticality


class EmploymentSettings(BaseSettings):
    """Configuration du connecteur emploi, sans exposer le secret de lecture."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    employment_database_url: SecretStr
    employment_owner: str = Field(min_length=1)
    employment_environment: Literal["local", "production"]
    employment_criticality: Criticality
    employment_error_max_length: int = Field(default=2000, ge=256, le=10_000)


@dataclass(frozen=True)
class EmploymentPipelineDefinition:
    provider: str
    pipeline_key: str
    display_name: str
    description: str
    expected_frequency_minutes: int

    @property
    def asset_external_id(self) -> str:
        return "sync-runs"

    @property
    def asset_logical_location(self) -> str:
        return f"app.sync_runs?provider={self.provider}"


PIPELINE_DEFINITIONS = (
    EmploymentPipelineDefinition(
        provider="france_travail",
        pipeline_key="emploi.france_travail",
        display_name="Offres France Travail",
        description="Synchronisation nationale des métadonnées d'offres France Travail.",
        expected_frequency_minutes=360,
    ),
    EmploymentPipelineDefinition(
        provider="la_bonne_alternance",
        pipeline_key="emploi.la_bonne_alternance",
        display_name="Offres La Bonne Alternance",
        description="Synchronisation nationale des métadonnées d'offres La Bonne Alternance.",
        expected_frequency_minutes=1440,
    ),
)

EXPECTED_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("text", "character varying"),
    "provider": ("text", "character varying"),
    "status": ("text", "character varying"),
    "started_at": ("timestamp with time zone",),
    "completed_at": ("timestamp with time zone",),
    "offers_seen": ("smallint", "integer", "bigint", "numeric"),
    "segments_expected": ("smallint", "integer", "bigint", "numeric"),
    "segments_completed": ("smallint", "integer", "bigint", "numeric"),
    "error_summary": ("text", "character varying"),
}
