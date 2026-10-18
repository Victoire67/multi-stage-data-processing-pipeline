"""Unit tests for environment-based settings."""

import pytest

from text_pipeline.config import Settings


def test_defaults_when_environment_is_empty() -> None:
    """Missing variables fall back to sensible defaults."""
    settings = Settings.from_env({})

    assert settings == Settings(database_url=None, log_level="INFO", log_format="json")


def test_reads_and_normalises_variables() -> None:
    """Values are read from the environment and case-normalised."""
    settings = Settings.from_env(
        {
            "PIPELINE_DATABASE_URL": "postgresql://u:p@h/db",
            "PIPELINE_LOG_LEVEL": "debug",
            "PIPELINE_LOG_FORMAT": "TEXT",
        }
    )

    assert settings.database_url == "postgresql://u:p@h/db"
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "text"


def test_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an explicit mapping os.environ is used."""
    monkeypatch.setenv("PIPELINE_DATABASE_URL", "postgresql://x")
    assert Settings.from_env().database_url == "postgresql://x"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [({"log_level": "LOUD"}, "log_level"), ({"log_format": "xml"}, "log_format")],
)
def test_invalid_values_are_rejected(kwargs: dict[str, str], match: str) -> None:
    """Unknown levels or formats raise ValueError."""
    with pytest.raises(ValueError, match=match):
        Settings(**kwargs)  # type: ignore[arg-type]
