"""Unit tests for the repositories (PostgreSQL driver is mocked)."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import psycopg
import pytest
from pytest_mock import MockerFixture

from text_pipeline.exceptions import StorageError
from text_pipeline.models import AnalysisResult, Sentiment
from text_pipeline.repository import (
    InMemorySentimentRepository,
    PostgresSentimentRepository,
    SentimentRepository,
)

RESULT = AnalysisResult("Bad!", "bad", Sentiment.NEGATIVE, -1.0, 0, 1)
NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
ROW = (3, "Bad!", "bad", "negative", -1.0, 0, 1, NOW)


# --------------------------------------------------------------------------- #
# In-memory repository
# --------------------------------------------------------------------------- #


def test_in_memory_repository_satisfies_protocol() -> None:
    """The in-memory repository can be injected wherever a repository is needed."""
    assert isinstance(InMemorySentimentRepository(), SentimentRepository)


def test_in_memory_repository_assigns_incrementing_ids() -> None:
    """Saved records get sequential ids and can be read back."""
    repo = InMemorySentimentRepository()

    first = repo.save(RESULT)
    second = repo.save(RESULT)

    assert (first.id, second.id) == (1, 2)
    assert repo.get(2) == second
    assert repo.get(99) is None
    assert repo.list_all() == [first, second]
    assert first.sentiment is Sentiment.NEGATIVE


# --------------------------------------------------------------------------- #
# PostgreSQL repository (psycopg.connect is replaced by a mock)
# --------------------------------------------------------------------------- #


@pytest.fixture
def connection(mocker: MockerFixture) -> MagicMock:
    """A mock psycopg connection usable as a context manager."""
    conn = mocker.MagicMock(name="connection")
    conn.__enter__.return_value = conn
    return conn  # type: ignore[no-any-return]


@pytest.fixture
def repo(connection: MagicMock, mocker: MockerFixture) -> PostgresSentimentRepository:
    """A repository whose connect function returns the mock connection."""
    connect = mocker.Mock(return_value=connection)
    return PostgresSentimentRepository("postgresql://test", connect=connect)


def _executed_sql(connection: MagicMock) -> str:
    query: Any = connection.execute.call_args.args[0]
    return query.as_string(None) if hasattr(query, "as_string") else str(query)


def test_postgres_repository_satisfies_protocol(
    repo: PostgresSentimentRepository,
) -> None:
    """The PostgreSQL repository implements the repository protocol."""
    assert isinstance(repo, SentimentRepository)


def test_initialize_schema_creates_table(
    repo: PostgresSentimentRepository, connection: MagicMock
) -> None:
    """The schema statement is idempotent (CREATE TABLE IF NOT EXISTS)."""
    repo.initialize_schema()

    assert 'CREATE TABLE IF NOT EXISTS "sentiment_results"' in _executed_sql(connection)


def test_save_inserts_and_returns_record(
    repo: PostgresSentimentRepository, connection: MagicMock
) -> None:
    """save() runs an INSERT ... RETURNING and maps the returned row."""
    connection.execute.return_value.fetchone.return_value = (3, NOW)

    record = repo.save(RESULT)

    assert "INSERT INTO" in _executed_sql(connection)
    params = connection.execute.call_args.args[1]
    assert params == ("Bad!", "bad", "negative", -1.0, 0, 1)
    assert record.id == 3
    assert record.created_at == NOW
    assert record.sentiment is Sentiment.NEGATIVE


def test_save_without_returned_row_raises(
    repo: PostgresSentimentRepository, connection: MagicMock
) -> None:
    """A missing RETURNING row is reported as a storage failure."""
    connection.execute.return_value.fetchone.return_value = None

    with pytest.raises(StorageError, match="no row"):
        repo.save(RESULT)


def test_get_and_list_map_rows(
    repo: PostgresSentimentRepository, connection: MagicMock
) -> None:
    """Rows are converted into StoredRecord objects."""
    connection.execute.return_value.fetchone.return_value = ROW
    connection.execute.return_value.fetchall.return_value = [ROW, ROW]

    assert repo.get(3) is not None
    assert repo.get(3).sentiment is Sentiment.NEGATIVE  # type: ignore[union-attr]
    assert [r.id for r in repo.list_all()] == [3, 3]


def test_get_missing_returns_none(
    repo: PostgresSentimentRepository, connection: MagicMock
) -> None:
    """An unknown id returns None."""
    connection.execute.return_value.fetchone.return_value = None
    assert repo.get(404) is None


@pytest.mark.parametrize(
    "operation",
    [
        lambda r: r.initialize_schema(),
        lambda r: r.save(RESULT),
        lambda r: r.get(1),
        lambda r: r.list_all(),
    ],
)
def test_driver_errors_become_storage_errors(
    repo: PostgresSentimentRepository, connection: MagicMock, operation: Any
) -> None:
    """psycopg errors are translated into StorageError, keeping the cause."""
    connection.execute.side_effect = psycopg.OperationalError("connection refused")

    with pytest.raises(StorageError, match="connection refused") as excinfo:
        operation(repo)
    assert isinstance(excinfo.value.__cause__, psycopg.Error)


def test_invalid_table_name_is_rejected() -> None:
    """Only simple identifiers are accepted as table names."""
    with pytest.raises(ValueError, match="table"):
        PostgresSentimentRepository("postgresql://x", table="bad; DROP TABLE x")
