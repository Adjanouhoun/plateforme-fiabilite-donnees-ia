from pfpd_ia.connectors.mobility.sanitizer import sanitize_error_message


def test_sanitizer_masks_dsn_password_and_sensitive_query_parameters() -> None:
    message = (
        "connection postgresql://reader:very-secret@database/mobility failed "
        "https://example.test/data?token=abc123&page=2 password=visible"
    )

    sanitized = sanitize_error_message(message, max_length=2000)

    assert sanitized is not None
    assert "very-secret" not in sanitized
    assert "abc123" not in sanitized
    assert "visible" not in sanitized
    assert "page=2" in sanitized


def test_sanitizer_limits_message_length() -> None:
    sanitized = sanitize_error_message("x" * 3000, max_length=2000)

    assert sanitized is not None
    assert len(sanitized) == 2000
    assert sanitized.endswith("…")
