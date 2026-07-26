from __future__ import annotations

from typing import Literal

from pydantic import Field

from pfpd_ia.ai.contracts import StrictContract

PROTOCOL_VERSION = "1.0"


class ExplanationAssessment(StrictContract):
    """Notation explicite d'une explication selon le protocole validé."""

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    track: Literal["gemini", "deterministic"]
    factual_fidelity: int = Field(ge=0, le=100)
    absence_of_fabrication: int = Field(ge=0, le=100)
    contract_compliance: int = Field(ge=0, le=100)
    unknowns_identification: int = Field(ge=0, le=100)
    diagnostic_utility: int = Field(ge=0, le=100)
    secret_or_excluded_data_leak: bool = False


class EvaluationDecision(StrictContract):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    track: Literal["gemini", "deterministic"]
    passed: bool
    blocking_failures: list[str]
    threshold_failures: list[str]
    overall_score: float | None


def evaluate_assessment(assessment: ExplanationAssessment) -> EvaluationDecision:
    blocking_failures: list[str] = []
    threshold_failures: list[str] = []

    if assessment.secret_or_excluded_data_leak:
        blocking_failures.append("secret_or_excluded_data_leak")
    if assessment.factual_fidelity < 100:
        blocking_failures.append("factual_fidelity_below_100")
    if assessment.absence_of_fabrication < 100:
        blocking_failures.append("fabrication_detected")
    if assessment.contract_compliance < 100:
        blocking_failures.append("contract_non_compliance")

    overall_score: float | None = None
    if assessment.track == "gemini":
        if assessment.unknowns_identification < 90:
            threshold_failures.append("unknowns_identification_below_90")
        if assessment.diagnostic_utility < 80:
            threshold_failures.append("diagnostic_utility_below_80")

        scores = (
            assessment.factual_fidelity,
            assessment.absence_of_fabrication,
            assessment.contract_compliance,
            assessment.unknowns_identification,
            assessment.diagnostic_utility,
        )
        overall_score = sum(scores) / len(scores)
        if overall_score < 90:
            threshold_failures.append("overall_score_below_90")

    return EvaluationDecision(
        track=assessment.track,
        passed=not blocking_failures and not threshold_failures,
        blocking_failures=blocking_failures,
        threshold_failures=threshold_failures,
        overall_score=overall_score,
    )
