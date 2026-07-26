from pfpd_ia.ai.evaluation import ExplanationAssessment, evaluate_assessment


def test_gemini_assessment_passes_all_validated_thresholds() -> None:
    decision = evaluate_assessment(
        ExplanationAssessment(
            track="gemini",
            factual_fidelity=100,
            absence_of_fabrication=100,
            contract_compliance=100,
            unknowns_identification=90,
            diagnostic_utility=80,
        )
    )

    assert decision.passed is True
    assert decision.overall_score == 94
    assert decision.blocking_failures == []
    assert decision.threshold_failures == []


def test_gemini_assessment_fails_on_each_blocking_rule() -> None:
    decision = evaluate_assessment(
        ExplanationAssessment(
            track="gemini",
            factual_fidelity=99,
            absence_of_fabrication=99,
            contract_compliance=99,
            unknowns_identification=100,
            diagnostic_utility=100,
            secret_or_excluded_data_leak=True,
        )
    )

    assert decision.passed is False
    assert decision.blocking_failures == [
        "secret_or_excluded_data_leak",
        "factual_fidelity_below_100",
        "fabrication_detected",
        "contract_non_compliance",
    ]


def test_gemini_assessment_fails_individual_and_overall_thresholds() -> None:
    decision = evaluate_assessment(
        ExplanationAssessment(
            track="gemini",
            factual_fidelity=100,
            absence_of_fabrication=100,
            contract_compliance=100,
            unknowns_identification=89,
            diagnostic_utility=60,
        )
    )

    assert decision.passed is False
    assert decision.overall_score == 89.8
    assert decision.threshold_failures == [
        "unknowns_identification_below_90",
        "diagnostic_utility_below_80",
        "overall_score_below_90",
    ]


def test_deterministic_track_does_not_require_diagnostic_leads() -> None:
    decision = evaluate_assessment(
        ExplanationAssessment(
            track="deterministic",
            factual_fidelity=100,
            absence_of_fabrication=100,
            contract_compliance=100,
            unknowns_identification=100,
            diagnostic_utility=0,
        )
    )

    assert decision.passed is True
    assert decision.overall_score is None
    assert decision.threshold_failures == []
