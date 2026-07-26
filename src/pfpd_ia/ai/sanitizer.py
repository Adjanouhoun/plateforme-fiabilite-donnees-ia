from __future__ import annotations

import re
from typing import Any

from pfpd_ia.ai.contracts import IncidentFactPackage

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|dsn|connection)",
    re.IGNORECASE,
)
_DSN = re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)://\S+", re.I)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+",
    re.I,
)


def _sanitize_string(value: str) -> str:
    value = _DSN.sub(REDACTED, value)
    value = _BEARER.sub(REDACTED, value)
    value = _EMAIL.sub(REDACTED, value)
    return _SENSITIVE_ASSIGNMENT.sub(REDACTED, value)


def sanitize_untrusted_value(value: Any) -> Any:
    """Retire les secrets connus d'une valeur JSON issue d'un connecteur."""

    if isinstance(value, dict):
        return {
            str(key): REDACTED
            if _SENSITIVE_KEY.search(str(key))
            else sanitize_untrusted_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_untrusted_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def sanitize_fact_package(package: IncidentFactPackage) -> IncidentFactPackage:
    """Produit une nouvelle instance validée, prête pour un fournisseur externe."""

    payload = package.model_dump(mode="python")
    check = payload["triggering_check"]
    check["observed_value"] = sanitize_untrusted_value(check["observed_value"])
    check["expected_rule"] = sanitize_untrusted_value(check["expected_rule"])
    check["evidence_reference"] = sanitize_untrusted_value(check["evidence_reference"])
    return IncidentFactPackage.model_validate(payload)
