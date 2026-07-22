"""Connecteur en lecture seule vers Data Pipeline Mobility."""

from pfpd_ia.connectors.mobility.collector import CollectionReport, collect_mobility_runs

__all__ = ["CollectionReport", "collect_mobility_runs"]
