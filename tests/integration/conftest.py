"""Fixtures that start a real PostgreSQL server with testcontainers-python."""

from collections.abc import Iterator

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from text_pipeline.repository import PostgresSentimentRepository

POSTGRES_IMAGE = "postgres:16-alpine"
TABLE = "sentiment_results"


def _docker_available() -> bool:
    """Return True when a Docker daemon is reachable."""
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Start one PostgreSQL container for the whole test session.

    Yields:
        A libpq DSN (``postgresql://user:pw@host:port/db``) for the container.
    """
    if not _docker_available():
        pytest.skip("Docker is not available - integration tests skipped")
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as container:
        yield container.get_connection_url()


@pytest.fixture
def repository(postgres_dsn: str) -> Iterator[PostgresSentimentRepository]:
    """A repository on a freshly created, empty results table."""
    repo = PostgresSentimentRepository(postgres_dsn, table=TABLE)
    repo.initialize_schema()
    yield repo
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")


@pytest.fixture
def fetch_rows(postgres_dsn: str) -> "RowFetcher":
    """Read the results table directly with SQL, bypassing the repository."""
    return RowFetcher(postgres_dsn)


class RowFetcher:
    """Callable helper returning all rows of the results table as dicts."""

    def __init__(self, dsn: str) -> None:
        """Store the DSN."""
        self.dsn = dsn

    def __call__(self) -> list[dict[str, object]]:
        """Return every row ordered by id."""
        with psycopg.connect(self.dsn) as conn:
            cursor = conn.execute(
                f"SELECT original_text, cleaned_text, sentiment, score, "
                f"positive_hits, negative_hits, created_at FROM {TABLE} ORDER BY id"
            )
            columns = [column.name for column in cursor.description or []]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
