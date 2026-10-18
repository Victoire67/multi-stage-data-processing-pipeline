"""Unit tests for the command-line interface."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from text_pipeline import cli
from text_pipeline.exceptions import StorageError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure no developer environment variables leak into the tests."""
    for name in ("PIPELINE_DATABASE_URL", "PIPELINE_LOG_LEVEL", "PIPELINE_LOG_FORMAT"):
        monkeypatch.delenv(name, raising=False)


def test_processes_texts_in_memory(capsys: pytest.CaptureFixture[str]) -> None:
    """Records are printed as JSON lines and the exit code is 0."""
    code = cli.main(["--in-memory", "I love it", "This is terrible"])

    out = capsys.readouterr().out.strip().splitlines()
    assert code == cli.EXIT_OK
    assert [json.loads(line)["sentiment"] for line in out] == [
        "positive",
        "negative",
    ]


def test_reads_inputs_from_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-blank lines of --file are processed."""
    source = tmp_path / "in.txt"
    source.write_text("great day\n\nawful day\n", encoding="utf-8")

    code = cli.main(["--in-memory", "--file", str(source), "--log-format", "text"])

    assert code == cli.EXIT_OK
    assert len(capsys.readouterr().out.strip().splitlines()) == 2


def test_failed_inputs_give_exit_code_1(capsys: pytest.CaptureFixture[str]) -> None:
    """Inputs that fail are reported on stderr."""
    code = cli.main(["--in-memory", "fine", "!!!"])

    captured = capsys.readouterr()
    assert code == cli.EXIT_FAILURES
    assert "failed input #1: [cleaner]" in captured.err


def test_no_input_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Running without any text is rejected."""
    assert cli.main(["--in-memory"]) == cli.EXIT_USAGE
    assert "no input text" in capsys.readouterr().err


def test_missing_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-existent --file path is reported."""
    assert cli.main(["--in-memory", "-f", str(tmp_path / "nope")]) == cli.EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_invalid_log_level_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown log level is rejected."""
    assert cli.main(["--in-memory", "--log-level", "loud", "x"]) == cli.EXIT_USAGE


def test_missing_database_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    """Without --database-url, env var or --in-memory the CLI refuses to run."""
    assert cli.main(["hello"]) == cli.EXIT_USAGE
    assert "no database configured" in capsys.readouterr().err


def test_uses_postgres_repository_from_env(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The DSN from the environment is used and the schema is initialised."""
    monkeypatch.setenv("PIPELINE_DATABASE_URL", "postgresql://env")
    repo_cls = mocker.patch.object(cli, "PostgresSentimentRepository")
    repo: Mock = repo_cls.return_value
    repo.save.side_effect = StorageError("db down")

    code = cli.main(["good"])

    repo_cls.assert_called_once_with("postgresql://env")
    repo.initialize_schema.assert_called_once_with()
    assert code == cli.EXIT_FAILURES
    assert "[storer] db down" in capsys.readouterr().err


def test_unreachable_database_exits_with_1(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failure while creating the schema is reported cleanly."""
    repo_cls = mocker.patch.object(cli, "PostgresSentimentRepository")
    repo_cls.return_value.initialize_schema.side_effect = StorageError("refused")

    assert cli.main(["--database-url", "postgresql://x", "hi"]) == cli.EXIT_FAILURES
    assert "refused" in capsys.readouterr().err
