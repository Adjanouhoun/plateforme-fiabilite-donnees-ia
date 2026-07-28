import json
import sys

from pfpd_ia.config import get_settings
from pfpd_ia.connectors.employment.collector import build_source_engine, collect_employment_runs
from pfpd_ia.connectors.employment.config import EmploymentSettings
from pfpd_ia.database import get_session_factory


def main() -> None:
    settings = EmploymentSettings()  # type: ignore[call-arg]
    source_engine = build_source_engine(settings)
    try:
        report = collect_employment_runs(source_engine, get_session_factory(), settings)
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
                {"error": "employment_collection_failed", "error_type": type(error).__name__}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
