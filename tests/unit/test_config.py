import pytest
from pydantic import ValidationError

from pfpd_ia.config import Settings


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="")


def test_explicit_test_configuration_is_accepted() -> None:
    settings = Settings(
        _env_file=None,
        app_environment="test",
        database_url="postgresql+psycopg://user:password@database/test",
    )

    assert settings.app_environment == "test"
    assert settings.log_level == "INFO"
