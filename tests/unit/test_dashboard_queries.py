from pfpd_ia.dashboard.queries import PortfolioKpis, derive_health_state


def test_health_state_is_derived_only_from_active_severity_and_run_presence() -> None:
    assert (
        derive_health_state(highest_active_severity="critical", latest_run_status="succeeded")
        == "incident_major"
    )
    assert (
        derive_health_state(highest_active_severity="error", latest_run_status="succeeded")
        == "incident_major"
    )
    assert (
        derive_health_state(highest_active_severity="warning", latest_run_status="succeeded")
        == "warning"
    )
    assert derive_health_state(highest_active_severity=None, latest_run_status=None) == "no_data"
    assert (
        derive_health_state(highest_active_severity=None, latest_run_status="failed") == "healthy"
    )


def test_kpi_rates_exclude_unfinished_runs_and_unmeasured_checks_from_denominators() -> None:
    kpis = PortfolioKpis(
        window_days=7,
        successful_runs=3,
        completed_runs=4,
        previous_successful_runs=0,
        previous_completed_runs=0,
        passed_checks=7,
        measured_checks=10,
        previous_passed_checks=0,
        previous_measured_checks=0,
        maximum_freshness_minutes=None,
        previous_maximum_freshness_minutes=None,
        active_incidents_by_severity={"critical": 0, "error": 0, "warning": 0, "info": 0},
        average_closed_incident_minutes=None,
        previous_average_closed_incident_minutes=None,
    )

    assert kpis.run_success_rate == 75.0
    assert kpis.check_conformity_rate == 70.0
    assert kpis.previous_run_success_rate is None
    assert kpis.previous_check_conformity_rate is None
