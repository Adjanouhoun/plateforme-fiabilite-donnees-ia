import json
import sys

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.mobility.collector import build_source_engine, collect_mobility_runs
from pfpd_ia.connectors.mobility.config import MobilitySettings
from pfpd_ia.database import get_session_factory


def main() -> None:
    mobility_settings = MobilitySettings()  # type: ignore[call-arg]
    source_engine = build_source_engine(mobility_settings)
    try:
        report = collect_mobility_runs(
            source_engine=source_engine,
            target_session_factory=get_session_factory(),
            settings=mobility_settings,
        )
    finally:
        source_engine.dispose()
    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        get_settings()
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": "mobility_collection_failed",
                    "error_type": type(error).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
