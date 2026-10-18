"""Persistence layer: where analysis results are stored.

:class:`~text_pipeline.stages.storer.DatabaseStorer` depends only on the
:class:`SentimentRepository` protocol (Dependency Inversion). Two
implementations are provided:

* :class:`PostgresSentimentRepository`: the production backend (psycopg 3);
* :class:`InMemorySentimentRepository`: a dependency-free backend for demos
  and fast tests.

A Redis or file-based backend can be added by implementing the same three
methods, with no change to the storer or the pipeline.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import psycopg
from psycopg import sql

from text_pipeline.exceptions import StorageError
from text_pipeline.models import AnalysisResult, Sentiment, StoredRecord

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {table} (
    id            BIGSERIAL PRIMARY KEY,
    original_text TEXT             NOT NULL,
    cleaned_text  TEXT             NOT NULL,
    sentiment     TEXT             NOT NULL
                  CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    score         DOUBLE PRECISION NOT NULL CHECK (score BETWEEN -1 AND 1),
    positive_hits INTEGER          NOT NULL CHECK (positive_hits >= 0),
    negative_hits INTEGER          NOT NULL CHECK (negative_hits >= 0),
    created_at    TIMESTAMPTZ      NOT NULL DEFAULT now()
)
"""

_COLUMNS = (
    "id, original_text, cleaned_text, sentiment, score, "
    "positive_hits, negative_hits, created_at"
)


@runtime_checkable
class SentimentRepository(Protocol):
    """Storage backend for analysis results."""

    def save(self, result: AnalysisResult) -> StoredRecord:
        """Persist ``result`` and return it with its assigned id.

        Args:
            result: The analysis result to store.

        Returns:
            The stored record.

        Raises:
            StorageError: If the result cannot be stored.
        """
        ...

    def get(self, record_id: int) -> StoredRecord | None:
        """Return the record with ``record_id`` or ``None`` if it is unknown.

        Args:
            record_id: Primary key of the record.

        Returns:
            The record, or ``None``.
        """
        ...

    def list_all(self) -> list[StoredRecord]:
        """Return every stored record ordered by id.

        Returns:
            All records.
        """
        ...


class InMemorySentimentRepository:
    """Keep records in a Python list (not persistent, not thread-safe)."""

    def __init__(self) -> None:
        """Create an empty repository."""
        self._records: list[StoredRecord] = []

    def save(self, result: AnalysisResult) -> StoredRecord:
        """Store ``result`` in memory with the next sequential id.

        Args:
            result: The analysis result to store.

        Returns:
            The stored record.
        """
        record = StoredRecord(
            id=len(self._records) + 1,
            original=result.original,
            cleaned=result.cleaned,
            sentiment=result.sentiment,
            score=result.score,
            positive_hits=result.positive_hits,
            negative_hits=result.negative_hits,
            created_at=datetime.now(tz=UTC),
        )
        self._records.append(record)
        return record

    def get(self, record_id: int) -> StoredRecord | None:
        """Return the record with ``record_id`` or ``None``.

        Args:
            record_id: Primary key of the record.

        Returns:
            The record, or ``None``.
        """
        return next((r for r in self._records if r.id == record_id), None)

    def list_all(self) -> list[StoredRecord]:
        """Return every stored record ordered by id.

        Returns:
            All records.
        """
        return list(self._records)


ConnectFn = Callable[..., Any]


class PostgresSentimentRepository:
    """Store analysis results in a PostgreSQL table using psycopg 3.

    A short-lived connection is opened per operation; psycopg commits the
    transaction when the ``with`` block exits successfully and rolls it back
    otherwise. Every driver error is translated into :class:`StorageError`.
    """

    def __init__(
        self,
        dsn: str,
        *,
        table: str = "sentiment_results",
        connect: ConnectFn = psycopg.connect,
    ) -> None:
        """Configure the repository.

        Args:
            dsn: libpq connection string, e.g.
                ``postgresql://user:pass@localhost:5432/db``.
            table: Name of the table to use (a simple SQL identifier).
            connect: Function used to open connections; injectable so unit
                tests can replace the real driver with a mock.

        Raises:
            ValueError: If ``table`` is not a simple identifier.
        """
        if not _IDENTIFIER.match(table):
            raise ValueError(f"invalid table name: {table!r}")
        self._dsn = dsn
        self._table = sql.Identifier(table)
        self._connect = connect

    def initialize_schema(self) -> None:
        """Create the results table if it does not exist yet.

        Raises:
            StorageError: If the statement fails.
        """
        query = sql.SQL(_CREATE_TABLE).format(table=self._table)
        self._execute(query, (), fetch=None, action="initialise schema")
        logger.info("database schema ready", extra={"event": "schema_ready"})

    def save(self, result: AnalysisResult) -> StoredRecord:
        """Insert ``result`` and return the stored record.

        Args:
            result: The analysis result to store.

        Returns:
            The stored record including the database id and timestamp.

        Raises:
            StorageError: If the insert fails.
        """
        query = sql.SQL(
            "INSERT INTO {table} (original_text, cleaned_text, sentiment, score,"
            " positive_hits, negative_hits) VALUES (%s, %s, %s, %s, %s, %s)"
            " RETURNING id, created_at"
        ).format(table=self._table)
        params = (
            result.original,
            result.cleaned,
            result.sentiment.value,
            result.score,
            result.positive_hits,
            result.negative_hits,
        )
        row = self._execute(query, params, fetch="one", action="save result")
        if row is None:
            raise StorageError("insert returned no row")
        record_id, created_at = row
        return StoredRecord(
            id=record_id,
            original=result.original,
            cleaned=result.cleaned,
            sentiment=result.sentiment,
            score=result.score,
            positive_hits=result.positive_hits,
            negative_hits=result.negative_hits,
            created_at=created_at,
        )

    def get(self, record_id: int) -> StoredRecord | None:
        """Fetch one record by id.

        Args:
            record_id: Primary key of the record.

        Returns:
            The record, or ``None`` if it does not exist.

        Raises:
            StorageError: If the query fails.
        """
        query = sql.SQL(f"SELECT {_COLUMNS} FROM {{table}} WHERE id = %s").format(
            table=self._table
        )
        row = self._execute(query, (record_id,), fetch="one", action="get record")
        return None if row is None else self._to_record(row)

    def list_all(self) -> list[StoredRecord]:
        """Fetch every record ordered by id.

        Returns:
            All records.

        Raises:
            StorageError: If the query fails.
        """
        query = sql.SQL(f"SELECT {_COLUMNS} FROM {{table}} ORDER BY id").format(
            table=self._table
        )
        rows = self._execute(query, (), fetch="all", action="list records")
        return [self._to_record(row) for row in rows]

    def _execute(
        self,
        query: sql.Composable,
        params: Sequence[Any],
        *,
        fetch: str | None,
        action: str,
    ) -> Any:
        """Run ``query`` in its own transaction and translate driver errors.

        Args:
            query: The composed SQL statement.
            params: Positional query parameters.
            fetch: ``"one"``, ``"all"`` or ``None`` (no result needed).
            action: Short description used in error messages.

        Returns:
            The fetched row(s), or ``None``.

        Raises:
            StorageError: If the driver raises any :class:`psycopg.Error`.
        """
        try:
            with self._connect(self._dsn) as conn:
                cursor = conn.execute(query, params)
                if fetch == "one":
                    return cursor.fetchone()
                if fetch == "all":
                    return cursor.fetchall()
                return None
        except psycopg.Error as error:
            raise StorageError(f"failed to {action}: {error}") from error

    @staticmethod
    def _to_record(row: Sequence[Any]) -> StoredRecord:
        """Convert a database row into a :class:`StoredRecord`."""
        return StoredRecord(
            id=row[0],
            original=row[1],
            cleaned=row[2],
            sentiment=Sentiment(row[3]),
            score=row[4],
            positive_hits=row[5],
            negative_hits=row[6],
            created_at=row[7],
        )
