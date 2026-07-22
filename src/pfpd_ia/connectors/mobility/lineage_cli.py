import json
import sys

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.mobility.config import (
    PIPELINE_DEFINITIONS,
    MobilityLineageSettings,
)
from pfpd_ia.connectors.mobility.lineage import collect_manifest_lineage, load_manifest
from pfpd_ia.database import get_session_factory


def main() -> None:
    settings = MobilityLineageSettings()  # type: ignore[call-arg]
    manifest = load_manifest(
        settings.mobility_dbt_manifest_path,
        expected_project_name=settings.mobility_dbt_project_name,
    )
    report = collect_manifest_lineage(
        manifest=manifest,
        target_session_factory=get_session_factory(),
        definitions=PIPELINE_DEFINITIONS,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    try:
        get_settings()
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": "mobility_lineage_collection_failed",
                    "error_type": type(error).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
