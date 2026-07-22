from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from pfpd_ia.models import CheckStatus, Severity


@dataclass(frozen=True)
class CheckEvaluation:
    check_type: str
    severity: Severity
    status: CheckStatus
    observed_value: dict[str, Any] | None
    expected_rule: dict[str, Any]
    evidence_reference: str | None = None


def evaluate_freshness(
    *,
    latest_success_at: datetime | None,
    evaluated_at: datetime,
    warning_after_minutes: int = 120,
    error_after_minutes: int = 360,
) -> CheckEvaluation:
    expected = {
        "warning_after_minutes": warning_after_minutes,
        "error_after_minutes": error_after_minutes,
        "basis": "latest_successful_run_end",
    }
    if latest_success_at is None:
        return CheckEvaluation(
            check_type="freshness",
            severity=Severity.WARNING,
            status=CheckStatus.NOT_MEASURED,
            observed_value=None,
            expected_rule=expected,
        )

    age_minutes = max(0.0, (evaluated_at - latest_success_at).total_seconds() / 60)
    severity = Severity.ERROR if age_minutes > error_after_minutes else Severity.WARNING
    status = CheckStatus.FAILED if age_minutes > warning_after_minutes else CheckStatus.PASSED
    return CheckEvaluation(
        check_type="freshness",
        severity=severity,
        status=status,
        observed_value={
            "age_minutes": round(age_minutes, 3),
            "latest_success_at": latest_success_at.isoformat(),
        },
        expected_rule=expected,
    )


def evaluate_volume(
    *,
    current_volume: int | None,
    reference_volumes: list[int],
    minimum_reference_count: int = 5,
    maximum_deviation_ratio: float = 0.5,
) -> CheckEvaluation:
    expected = {
        "minimum_reference_count": minimum_reference_count,
        "maximum_deviation_ratio": maximum_deviation_ratio,
        "baseline": "median_previous_successful_runs",
    }
    if current_volume is None or len(reference_volumes) < minimum_reference_count:
        return CheckEvaluation(
            check_type="volume",
            severity=Severity.WARNING,
            status=CheckStatus.NOT_MEASURED,
            observed_value={
                "current_volume": current_volume,
                "reference_count": len(reference_volumes),
            },
            expected_rule=expected,
        )

    selected_references = reference_volumes[:minimum_reference_count]
    baseline = float(median(selected_references))
    if baseline == 0:
        deviation_ratio = 0.0 if current_volume == 0 else None
        failed = current_volume != 0
    else:
        deviation_ratio = abs(current_volume - baseline) / baseline
        failed = deviation_ratio > maximum_deviation_ratio

    return CheckEvaluation(
        check_type="volume",
        severity=Severity.WARNING,
        status=CheckStatus.FAILED if failed else CheckStatus.PASSED,
        observed_value={
            "current_volume": current_volume,
            "reference_count": minimum_reference_count,
            "reference_median": baseline,
            "deviation_ratio": None if deviation_ratio is None else round(deviation_ratio, 6),
        },
        expected_rule=expected,
    )


def evaluate_uniqueness(*, total_count: int | None, distinct_count: int | None) -> CheckEvaluation:
    expected = {"duplicate_count": 0, "field": "pipeline_run_id"}
    if total_count is None or distinct_count is None:
        return CheckEvaluation(
            check_type="uniqueness",
            severity=Severity.ERROR,
            status=CheckStatus.NOT_MEASURED,
            observed_value=None,
            expected_rule=expected,
        )
    duplicate_count = total_count - distinct_count
    return CheckEvaluation(
        check_type="uniqueness",
        severity=Severity.ERROR,
        status=CheckStatus.FAILED if duplicate_count else CheckStatus.PASSED,
        observed_value={
            "total_count": total_count,
            "distinct_count": distinct_count,
            "duplicate_count": duplicate_count,
        },
        expected_rule=expected,
    )


def evaluate_consistency(
    *, rows_read: int | None, rows_written: int | None, rows_unchanged: int | None
) -> CheckEvaluation:
    expected = {"formula": "rows_read = rows_written + rows_unchanged"}
    if rows_read is None or rows_written is None or rows_unchanged is None:
        return CheckEvaluation(
            check_type="volume_consistency",
            severity=Severity.ERROR,
            status=CheckStatus.NOT_MEASURED,
            observed_value={
                "rows_read": rows_read,
                "rows_written": rows_written,
                "rows_unchanged": rows_unchanged,
            },
            expected_rule=expected,
        )

    classified = rows_written + rows_unchanged
    return CheckEvaluation(
        check_type="volume_consistency",
        severity=Severity.ERROR,
        status=CheckStatus.FAILED if rows_read != classified else CheckStatus.PASSED,
        observed_value={
            "rows_read": rows_read,
            "classified_rows": classified,
            "difference": rows_read - classified,
        },
        expected_rule=expected,
    )


def evaluate_schema(
    *, actual_columns: dict[str, str], expected_columns: dict[str, tuple[str, ...]]
) -> CheckEvaluation:
    missing = sorted(set(expected_columns) - set(actual_columns))
    incompatible = {
        column: {"actual": actual_columns[column], "allowed": list(allowed_types)}
        for column, allowed_types in expected_columns.items()
        if column in actual_columns and actual_columns[column] not in allowed_types
    }
    return CheckEvaluation(
        check_type="schema",
        severity=Severity.ERROR,
        status=CheckStatus.FAILED if missing or incompatible else CheckStatus.PASSED,
        observed_value={
            "missing_columns": missing,
            "incompatible_columns": incompatible,
            "observed_column_count": len(actual_columns),
        },
        expected_rule={
            "required_columns": {
                column: list(allowed_types) for column, allowed_types in expected_columns.items()
            }
        },
    )
