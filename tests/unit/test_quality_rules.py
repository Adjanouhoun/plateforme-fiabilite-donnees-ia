from datetime import UTC, datetime, timedelta

from pfpd_ia.models import CheckStatus, Severity
from pfpd_ia.quality.rules import (
    evaluate_consistency,
    evaluate_freshness,
    evaluate_schema,
    evaluate_uniqueness,
    evaluate_volume,
)


def test_freshness_uses_validated_warning_and_error_thresholds() -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)

    passing = evaluate_freshness(latest_success_at=now - timedelta(minutes=120), evaluated_at=now)
    warning = evaluate_freshness(latest_success_at=now - timedelta(minutes=121), evaluated_at=now)
    error = evaluate_freshness(latest_success_at=now - timedelta(minutes=361), evaluated_at=now)

    assert passing.status == CheckStatus.PASSED
    assert warning.status == CheckStatus.FAILED
    assert warning.severity == Severity.WARNING
    assert error.status == CheckStatus.FAILED
    assert error.severity == Severity.ERROR


def test_freshness_without_success_is_not_measured() -> None:
    evaluation = evaluate_freshness(
        latest_success_at=None, evaluated_at=datetime(2026, 7, 22, tzinfo=UTC)
    )

    assert evaluation.status == CheckStatus.NOT_MEASURED


def test_volume_requires_five_previous_successful_references() -> None:
    evaluation = evaluate_volume(current_volume=100, reference_volumes=[100, 100, 100, 100])

    assert evaluation.status == CheckStatus.NOT_MEASURED
    assert evaluation.observed_value == {"current_volume": 100, "reference_count": 4}


def test_volume_fails_only_above_fifty_percent_deviation() -> None:
    boundary = evaluate_volume(current_volume=150, reference_volumes=[100, 100, 100, 100, 100])
    anomaly = evaluate_volume(current_volume=151, reference_volumes=[100, 100, 100, 100, 100])

    assert boundary.status == CheckStatus.PASSED
    assert anomaly.status == CheckStatus.FAILED


def test_uniqueness_and_consistency_detect_reproducible_failures() -> None:
    duplicate = evaluate_uniqueness(total_count=10, distinct_count=9)
    inconsistent = evaluate_consistency(rows_read=10, rows_written=7, rows_unchanged=2)
    unavailable = evaluate_consistency(rows_read=10, rows_written=None, rows_unchanged=2)

    assert duplicate.status == CheckStatus.FAILED
    assert duplicate.observed_value["duplicate_count"] == 1
    assert inconsistent.status == CheckStatus.FAILED
    assert unavailable.status == CheckStatus.NOT_MEASURED


def test_uniqueness_without_source_measure_is_not_measured() -> None:
    evaluation = evaluate_uniqueness(total_count=None, distinct_count=None)

    assert evaluation.status == CheckStatus.NOT_MEASURED


def test_schema_reports_missing_and_incompatible_columns() -> None:
    evaluation = evaluate_schema(
        actual_columns={"run_id": "text", "started_at": "text"},
        expected_columns={
            "run_id": ("text", "character varying"),
            "started_at": ("timestamp with time zone",),
            "status": ("text", "character varying"),
        },
    )

    assert evaluation.status == CheckStatus.FAILED
    assert evaluation.observed_value["missing_columns"] == ["status"]
    assert evaluation.observed_value["incompatible_columns"] == {
        "started_at": {"actual": "text", "allowed": ["timestamp with time zone"]}
    }
