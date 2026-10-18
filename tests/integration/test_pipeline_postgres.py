"""Integration tests: the full pipeline against a real PostgreSQL container."""

import io
import json
from datetime import datetime

import pytest

from tests.integration.conftest import RowFetcher
from text_pipeline import cli
from text_pipeline.exceptions import CleaningError, StorageError
from text_pipeline.logging_config import configure_logging
from text_pipeline.models import AnalysisResult, Sentiment
from text_pipeline.pipeline import build_pipeline
from text_pipeline.repository import PostgresSentimentRepository

pytestmark = pytest.mark.integration


def test_full_pipeline_stores_structured_result(
    repository: PostgresSentimentRepository, fetch_rows: RowFetcher
) -> None:
    """Raw text goes through every stage and lands in PostgreSQL correctly."""
    pipeline = build_pipeline(repository)

    record = pipeline.run("<p>I LOVE this product, it's <b>excellent</b>!!!</p>")

    rows = fetch_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["original_text"] == (
        "<p>I LOVE this product, it's <b>excellent</b>!!!</p>"
    )
    assert row["cleaned_text"] == "i love this product it's excellent"
    assert row["sentiment"] == "positive"
    assert row["score"] == 1.0
    assert (row["positive_hits"], row["negative_hits"]) == (2, 0)
    assert isinstance(row["created_at"], datetime)
    assert record.id > 0
    assert repository.get(record.id) == record


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Terrible service and a broken product", "negative"),
        ("This is not bad at all", "positive"),
        ("I don't love it", "negative"),
        ("The parcel arrived on Monday", "neutral"),
    ],
)
def test_sentiment_labels_are_persisted(
    repository: PostgresSentimentRepository,
    fetch_rows: RowFetcher,
    text: str,
    expected: str,
) -> None:
    """The label computed by the analyzer is what ends up in the database."""
    build_pipeline(repository).run(text)

    assert fetch_rows()[0]["sentiment"] == expected


def test_batch_stores_valid_inputs_and_skips_invalid_ones(
    repository: PostgresSentimentRepository, fetch_rows: RowFetcher
) -> None:
    """Invalid inputs are reported and never written to the database."""
    batch = build_pipeline(repository).run_batch(
        ["Great job", "   ", "Awful experience", "!!! ???", "Nice and fast"]
    )

    assert batch.succeeded == 3
    assert [f.index for f in batch.failures] == [1, 3]
    assert all(isinstance(f.error, CleaningError) for f in batch.failures)
    assert [r["sentiment"] for r in fetch_rows()] == [
        "positive",
        "negative",
        "positive",
    ]
    assert [r.id for r in repository.list_all()] == [r.id for r in batch.records]


def test_database_constraints_surface_as_storage_error(
    repository: PostgresSentimentRepository, fetch_rows: RowFetcher
) -> None:
    """A CHECK-constraint violation from PostgreSQL becomes StorageError."""
    invalid = AnalysisResult("x", "x", Sentiment.POSITIVE, 2.5, 1, 0)

    with pytest.raises(StorageError, match="failed to save result"):
        repository.save(invalid)
    assert fetch_rows() == []


def test_unreachable_database_raises_storage_error() -> None:
    """Connection failures are translated into StorageError."""
    repo = PostgresSentimentRepository(
        "postgresql://nobody:wrong@127.0.0.1:1/missing?connect_timeout=2"
    )
    pipeline = build_pipeline(repo)

    with pytest.raises(StorageError):
        pipeline.run("hello great world")


def test_logs_trace_one_run_across_all_stages(
    repository: PostgresSentimentRepository,
) -> None:
    """Every stage logs its state and all lines share the same run_id."""
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)

    build_pipeline(repository).run("Wonderful staff", run_id="trace-me")

    entries = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert {e["run_id"] for e in entries} == {"trace-me"}
    completed = [e["stage"] for e in entries if e["message"] == "stage completed"]
    assert completed == ["cleaner", "analyzer", "storer"]
    assert entries[-1]["message"] == "pipeline completed"


def test_cli_writes_to_postgres(
    postgres_dsn: str,
    repository: PostgresSentimentRepository,
    fetch_rows: RowFetcher,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI end to end: arguments in, rows in PostgreSQL, JSON lines out."""
    code = cli.main(["--database-url", postgres_dsn, "Superb!", "Worst ever"])

    assert code == cli.EXIT_OK
    assert [r["sentiment"] for r in fetch_rows()] == ["positive", "negative"]
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [p["cleaned"] for p in printed] == ["superb", "worst ever"]
