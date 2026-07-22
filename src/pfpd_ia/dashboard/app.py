from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from pfpd_ia.dashboard.queries import (
    PipelineSummary,
    PortfolioKpis,
    acknowledge,
    close,
    get_pipeline,
    get_portfolio_kpis,
    list_assets,
    list_checks,
    list_incident_events,
    list_incident_exposure,
    list_incidents,
    list_lineage,
    list_pipeline_summaries,
    list_runs,
)
from pfpd_ia.database import get_session_factory

HEALTH_LABELS = {
    "incident_major": "Incident majeur",
    "warning": "Avertissement",
    "no_data": "Sans données",
    "healthy": "Sain",
}
STATUS_LABELS = {
    "succeeded": "Réussie",
    "failed": "Échouée",
    "pending": "En attente",
    "running": "En cours",
    "cancelled": "Annulée",
    "unknown": "Inconnu",
    "passed": "Conforme",
    "not_measured": "Non mesuré",
    "open": "Ouvert",
    "acknowledged": "Acquitté",
    "resolved": "Résolu",
    "closed": "Clos",
}
SEVERITY_LABELS = {
    "info": "Information",
    "warning": "Avertissement",
    "error": "Erreur",
    "critical": "Critique",
}


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Indisponible"
    return value.astimezone(UTC).strftime("%d/%m/%Y %H:%M UTC")


def _format_json(value: Any) -> str:
    if value is None:
        return "Non mesuré"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_summaries() -> list[PipelineSummary]:
    factory = get_session_factory()
    with factory() as session:
        return list_pipeline_summaries(session)


def _load_portfolio_kpis(pipeline_keys: list[str], window_days: int) -> PortfolioKpis:
    factory = get_session_factory()
    with factory() as session:
        return get_portfolio_kpis(
            session,
            pipeline_keys=pipeline_keys,
            window_days=window_days,
        )


def _format_rate(value: float | None) -> str:
    return "Non mesuré" if value is None else f"{value:.1f} %"


def _format_minutes(value: float | None) -> str:
    if value is None:
        return "Non mesuré"
    if value >= 1_440:
        return f"{value / 1_440:.1f} j"
    if value >= 60:
        return f"{value / 60:.1f} h"
    return f"{value:.1f} min"


def _delta(current: float | None, previous: float | None, suffix: str) -> str | None:
    if current is None or previous is None:
        return None
    return f"{current - previous:+.1f} {suffix}"


def _render_period_kpis(filtered: list[PipelineSummary]) -> None:
    st.subheader("Indicateurs sur période")
    window_days = st.radio(
        "Fenêtre d’analyse",
        [7, 30],
        horizontal=True,
        format_func=lambda days: f"{days} jours",
    )
    kpis = _load_portfolio_kpis([summary.pipeline_key for summary in filtered], window_days)
    metrics = st.columns(5)
    metrics[0].metric(
        "Réussite des exécutions",
        _format_rate(kpis.run_success_rate),
        _delta(kpis.run_success_rate, kpis.previous_run_success_rate, "points"),
        help=(
            "Exécutions réussies divisées par les exécutions terminées. "
            "Une exécution est terminée lorsque sa date de fin est renseignée."
        ),
    )
    metrics[1].metric(
        "Conformité des contrôles",
        _format_rate(kpis.check_conformity_rate),
        _delta(kpis.check_conformity_rate, kpis.previous_check_conformity_rate, "points"),
        help="Contrôles conformes divisés par les contrôles mesurés. Non mesuré est exclu.",
    )
    metrics[2].metric(
        "Retard maximal",
        _format_minutes(kpis.maximum_freshness_minutes),
        _delta(
            kpis.maximum_freshness_minutes,
            kpis.previous_maximum_freshness_minutes,
            "min",
        ),
        delta_color="inverse",
        help="Valeur maximale age_minutes des contrôles de fraîcheur sur la période.",
    )
    active_total = sum(kpis.active_incidents_by_severity.values())
    metrics[3].metric(
        "Incidents actifs",
        active_total,
        help="Incidents actuellement ouverts ou acquittés, répartis par sévérité ci-dessous.",
    )
    metrics[4].metric(
        "Durée moyenne de clôture",
        _format_minutes(kpis.average_closed_incident_minutes),
        _delta(
            kpis.average_closed_incident_minutes,
            kpis.previous_average_closed_incident_minutes,
            "min",
        ),
        delta_color="inverse",
        help="Moyenne de closed_at - opened_at pour les incidents clôturés sur la période.",
    )
    severity = kpis.active_incidents_by_severity
    st.caption(
        "Incidents actifs par sévérité — "
        f"Critique : {severity['critical']} · Erreur : {severity['error']} · "
        f"Avertissement : {severity['warning']} · Information : {severity['info']}"
    )
    st.caption(
        "Les variations comparent cette fenêtre aux "
        f"{window_days} jours précédents. Une valeur non mesurée n’est jamais assimilée à zéro."
    )


def _render_header() -> None:
    st.title("Fiabilité des données pour l’IA")
    st.caption(
        "Vue commune des pipelines — faits mesurés, contrôles déterministes et incidents traçables."
    )


def _render_portfolio(summaries: list[PipelineSummary]) -> None:
    st.header("Portefeuille de pipelines")
    if not summaries:
        st.info("Aucun pipeline actif n’est enregistré.")
        return

    environments = sorted({summary.environment for summary in summaries})
    criticalities = sorted({summary.criticality for summary in summaries})
    states = sorted({summary.health_state for summary in summaries})

    filter_columns = st.columns(3)
    selected_environments = filter_columns[0].multiselect(
        "Environnement", environments, default=environments
    )
    selected_criticalities = filter_columns[1].multiselect(
        "Criticité", criticalities, default=criticalities
    )
    selected_states = filter_columns[2].multiselect(
        "État",
        states,
        default=states,
        format_func=lambda value: HEALTH_LABELS[value],
    )
    filtered = [
        summary
        for summary in summaries
        if summary.environment in selected_environments
        and summary.criticality in selected_criticalities
        and summary.health_state in selected_states
    ]

    metrics = st.columns(4)
    metrics[0].metric("Pipelines affichés", len(filtered))
    metrics[1].metric("Incidents actifs", sum(item.active_incidents for item in filtered))
    metrics[2].metric("Contrôles en échec", sum(item.failed_checks for item in filtered))
    metrics[3].metric("Non mesurés", sum(item.not_measured_checks for item in filtered))

    if not filtered:
        st.info("Aucun pipeline ne correspond aux filtres sélectionnés.")
        return

    _render_period_kpis(filtered)

    st.dataframe(
        [
            {
                "Pipeline": item.display_name,
                "État": HEALTH_LABELS[item.health_state],
                "Environnement": item.environment,
                "Criticité": item.criticality,
                "Dernière exécution": _format_datetime(item.latest_run_at),
                "Statut du run": STATUS_LABELS.get(
                    item.latest_run_status or "unknown", "Indisponible"
                ),
                "Lignes lues": item.latest_rows_read,
                "Incidents actifs": item.active_incidents,
                "Contrôles en échec": item.failed_checks,
                "Non mesurés": item.not_measured_checks,
            }
            for item in filtered
        ],
        hide_index=True,
        width="stretch",
    )


def _render_runs(runs: list[dict[str, Any]]) -> None:
    if not runs:
        st.info("Aucune exécution n’est disponible pour ce pipeline.")
        return
    st.dataframe(
        [
            {
                "Début": _format_datetime(run["started_at"]),
                "Fin": _format_datetime(run["ended_at"]),
                "Statut": STATUS_LABELS.get(run["status"], run["status"]),
                "Lues": run["rows_read"],
                "Écrites": run["rows_written"],
                "Rejetées": run["rows_rejected"]
                if run["rows_rejected"] is not None
                else "Non mesuré",
                "Inchangées": run["rows_unchanged"],
                "Identifiant source": run["external_run_id"],
            }
            for run in runs
        ],
        hide_index=True,
        width="stretch",
    )


def _render_checks(checks: list[dict[str, Any]]) -> None:
    if not checks:
        st.info("Aucun contrôle n’est disponible pour ce pipeline.")
        return
    st.dataframe(
        [
            {
                "Date": _format_datetime(check["checked_at"]),
                "Contrôle": check["check_type"],
                "Résultat": STATUS_LABELS.get(check["status"], check["status"]),
                "Sévérité": SEVERITY_LABELS.get(check["severity"], check["severity"]),
                "Actif": check["asset_name"],
                "Exécution": check["external_run_id"] or "Contrôle global",
                "Valeur observée": _format_json(check["observed_value"]),
                "Règle": _format_json(check["expected_rule"]),
                "Preuve": check["evidence_reference"],
            }
            for check in checks
        ],
        hide_index=True,
        width="stretch",
    )


def _render_incidents(pipeline_key: str, operator_name: str) -> None:
    factory = get_session_factory()
    with factory() as session:
        incidents = list_incidents(session, pipeline_key)
        exposure = list_incident_exposure(session, pipeline_key)
        events_by_incident = {
            incident["id"]: list_incident_events(session, incident["id"]) for incident in incidents
        }
    if not incidents:
        st.info("Aucun incident n’est enregistré pour ce pipeline.")
        return
    if not operator_name:
        st.info(
            "Mode lecture seule : configurez OPERATOR_NAME pour acquitter ou clôturer un incident."
        )

    exposure_by_incident = {
        incident["id"]: [row for row in exposure if row["incident_id"] == incident["id"]]
        for incident in incidents
    }
    for incident in incidents:
        label = (
            f"{SEVERITY_LABELS.get(incident['severity'], incident['severity'])} — "
            f"{STATUS_LABELS.get(incident['status'], incident['status'])} — {incident['title']}"
        )
        with st.expander(label, expanded=incident["status"] in {"open", "acknowledged"}):
            st.write(f"Ouvert le : {_format_datetime(incident['opened_at'])}")
            st.write(
                f"Contrôle déclencheur : {incident['triggering_check_type'] or 'Indisponible'}"
            )
            st.write(
                "Impact métier : "
                + (incident["business_impact"] or "Inconnu — aucune mesure ou déclaration")
            )
            st.caption(
                "L’exposition technique ci-dessous est calculée depuis le lineage prouvé. "
                "Elle ne constitue pas un impact métier mesuré."
            )
            incident_exposure = exposure_by_incident[incident["id"]]
            if incident_exposure:
                st.dataframe(
                    [
                        {
                            "Niveau": row["depth"],
                            "Actif": row["asset_name"],
                            "Type": row["asset_type"],
                            "Emplacement": row["logical_location"],
                            "Preuve": row["evidence_origin"] or "Actif du contrôle déclencheur",
                        }
                        for row in incident_exposure
                    ],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("Aucune exposition technique calculable à partir des preuves disponibles.")
            events = events_by_incident[incident["id"]]
            st.dataframe(
                [
                    {
                        "Date": _format_datetime(event["occurred_at"]),
                        "Événement": event["event_type"],
                        "Acteur": event["actor"],
                        "Détails": _format_json(event["details"]),
                    }
                    for event in events
                ],
                hide_index=True,
                width="stretch",
            )
            if (
                operator_name
                and incident["status"] == "open"
                and st.button("Acquitter", key=f"ack-{incident['id']}")
            ):
                acknowledge(factory, incident_id=incident["id"], actor=operator_name)
                st.success("Incident acquitté.")
                st.rerun()
            if (
                operator_name
                and incident["status"] == "resolved"
                and st.button("Clôturer", key=f"close-{incident['id']}")
            ):
                close(factory, incident_id=incident["id"], actor=operator_name)
                st.success("Incident clôturé.")
                st.rerun()


def _render_assets_and_lineage(pipeline_key: str) -> None:
    factory = get_session_factory()
    with factory() as session:
        assets = list_assets(session, pipeline_key)
        lineage = list_lineage(session, pipeline_key)
    st.subheader("Actifs")
    if assets:
        st.dataframe(
            [
                {
                    "Nom": asset["name"],
                    "Type": asset["asset_type"],
                    "Système": asset["source_system"],
                    "Emplacement logique": asset["logical_location"],
                    "Propriétaire": asset["owner"],
                    "Sensibilité": asset["sensitivity"],
                    "Contrat de schéma": _format_json(asset["schema_contract"]),
                }
                for asset in assets
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Aucun actif n’est enregistré pour ce pipeline.")

    st.subheader("Dépendances")
    if lineage:
        st.dataframe(lineage, hide_index=True, width="stretch")
    else:
        st.info("Aucune dépendance prouvée n’est disponible. Aucun graphe n’est inventé.")


def _render_pipeline_detail(summaries: list[PipelineSummary], operator_name: str) -> None:
    st.header("Détail d’un pipeline")
    if not summaries:
        st.info("Aucun pipeline actif n’est enregistré.")
        return
    selected_key = st.selectbox(
        "Pipeline",
        [summary.pipeline_key for summary in summaries],
        format_func=lambda key: next(
            summary.display_name for summary in summaries if summary.pipeline_key == key
        ),
    )
    summary = next(item for item in summaries if item.pipeline_key == selected_key)
    factory = get_session_factory()
    with factory() as session:
        pipeline = get_pipeline(session, selected_key)
        runs = list_runs(session, selected_key)
        checks = list_checks(session, selected_key)
    if pipeline is None:
        st.error("Le pipeline sélectionné n’existe plus.")
        return

    st.subheader(pipeline["display_name"])
    metadata = st.columns(4)
    metadata[0].metric("État", HEALTH_LABELS[summary.health_state])
    metadata[1].metric("Environnement", pipeline["environment"])
    metadata[2].metric("Criticité", pipeline["criticality"])
    metadata[3].metric("Fréquence", f"{pipeline['expected_frequency_minutes']} min")
    st.caption(
        f"Propriétaire : {pipeline['owner']} — {pipeline['description'] or 'Sans description'}"
    )

    runs_tab, checks_tab, incidents_tab, assets_tab = st.tabs(
        ["Exécutions", "Contrôles", "Incidents", "Actifs et dépendances"]
    )
    with runs_tab:
        _render_runs(runs)
    with checks_tab:
        _render_checks(checks)
    with incidents_tab:
        _render_incidents(selected_key, operator_name)
    with assets_tab:
        _render_assets_and_lineage(selected_key)


def main() -> None:
    st.set_page_config(page_title="Fiabilité des données", page_icon="◉", layout="wide")
    _render_header()
    operator_name = os.getenv("OPERATOR_NAME", "").strip()
    with st.sidebar:
        st.subheader("Navigation")
        page = st.radio("Vue", ["Portefeuille", "Détail d’un pipeline"])
        if st.button("Actualiser les données", width="stretch"):
            st.rerun()
        st.caption(f"Actualisé : {datetime.now(UTC).strftime('%d/%m/%Y %H:%M UTC')}")
        st.caption(f"Opérateur : {operator_name}" if operator_name else "Opérateur : non configuré")

    try:
        summaries = _load_summaries()
        if page == "Portefeuille":
            _render_portfolio(summaries)
        else:
            _render_pipeline_detail(summaries, operator_name)
    except (SQLAlchemyError, ValueError):
        st.error("La base d’observabilité est indisponible ou contient un état incompatible.")


if __name__ == "__main__":
    main()
