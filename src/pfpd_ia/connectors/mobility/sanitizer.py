import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "password",
    "secret",
    "token",
}

KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret|authorization)\b"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
DSN_PATTERN = re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:)([^@\s]+)(@)")
URL_PATTERN = re.compile(r"https?://[^\s]+")


def _sanitize_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return "[URL_MASQUÉE]"

    if not parts.query:
        return raw_url

    sanitized_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        sanitized_query.append((key, "[MASQUÉ]" if key.lower() in SENSITIVE_KEYS else value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(sanitized_query), parts.fragment)
    )


def sanitize_error_message(message: str | None, max_length: int) -> str | None:
    if message is None:
        return None

    sanitized = DSN_PATTERN.sub(r"\1[MASQUÉ]\3", message)
    sanitized = KEY_VALUE_PATTERN.sub(r"\1\2[MASQUÉ]", sanitized)
    sanitized = URL_PATTERN.sub(_sanitize_url, sanitized)
    sanitized = sanitized.strip()

    if not sanitized:
        return None
    if len(sanitized) <= max_length:
        return sanitized
    return sanitized[: max_length - 1] + "…"
