"""Unit tests for the DatabaseStorer stage (repository is mocked)."""

import logging
from datetime import UTC, datetime

import pytest
from pytest_mock import MockerFixture

from text_pipeline.exceptions import StorageError
from text_pipeline.models import AnalysisResult, Sentiment, StoredRecord
from text_pipeline.repository import SentimentRepository
from text_pipeline.stages.base import PipelineStage
from text_pipeline.stages.storer import DatabaseStorer

RESULT = AnalysisResult("Great!", "great", Sentiment.POSITIVE, 1.0, 1, 0)
RECORD = StoredRecord(
    1,
    "Great!",
    "great",
    Sentiment.POSITIVE,
    1.0,
    1,
    0,
    datetime(2026, 1, 1, tzinfo=UTC),
)


@pytest.fixture
def repository(mocker: MockerFixture) -> SentimentRepository:
    """A mock that satisfies the SentimentRepository protocol."""
    repo = mocker.Mock(spec=SentimentRepository)
    repo.save.return_value = RECORD
    return repo  # type: ignore[no-any-return]


def test_is_a_pipeline_stage(repository: SentimentRepository) -> None:
    """The storer implements the common stage interface."""
    storer = DatabaseStorer(repository)
    assert isinstance(storer, PipelineStage)
    assert storer.name == "storer"


def test_delegates_to_repository(repository: SentimentRepository) -> None:
    """The storer hands the analysis result to the injected repository."""
    record = DatabaseStorer(repository).process(RESULT)

    repository.save.assert_called_once_with(RESULT)  # type: ignore[attr-defined]
    assert record is RECORD


def test_rejects_wrong_input_type(repository: SentimentRepository) -> None:
    """Only AnalysisResult objects can be stored."""
    with pytest.raises(StorageError, match="expected AnalysisResult"):
        DatabaseStorer(repository).process("not a result")  # type: ignore[arg-type]
    repository.save.assert_not_called()  # type: ignore[attr-defined]


def test_storage_errors_propagate_unchanged(repository: SentimentRepository) -> None:
    """A StorageError raised by the repository is re-raised as-is."""
    original = StorageError("db down")
    repository.save.side_effect = original  # type: ignore[attr-defined]

    with pytest.raises(StorageError) as excinfo:
        DatabaseStorer(repository).process(RESULT)
    assert excinfo.value is original


def test_unexpected_errors_are_wrapped(repository: SentimentRepository) -> None:
    """Any other exception is converted into StorageError with its cause."""
    repository.save.side_effect = ConnectionResetError("reset")  # type: ignore[attr-defined]

    with pytest.raises(StorageError, match="unexpected error") as excinfo:
        DatabaseStorer(repository).process(RESULT)
    assert isinstance(excinfo.value.__cause__, ConnectionResetError)


def test_logs_state_after_stage(
    repository: SentimentRepository, caplog: pytest.LogCaptureFixture
) -> None:
    """A structured 'stage completed' record with the stored id is emitted."""
    with caplog.at_level(logging.INFO, logger="text_pipeline"):
        DatabaseStorer(repository).process(RESULT)

    record = next(r for r in caplog.records if r.message == "stage completed")
    assert record.stage == "storer"  # type: ignore[attr-defined]
    assert record.state["id"] == 1  # type: ignore[attr-defined]


def test_logs_failure(
    repository: SentimentRepository, caplog: pytest.LogCaptureFixture
) -> None:
    """Failures are logged before being raised."""
    repository.save.side_effect = StorageError("db down")  # type: ignore[attr-defined]

    with (
        caplog.at_level(logging.WARNING, logger="text_pipeline"),
        pytest.raises(StorageError),
    ):
        DatabaseStorer(repository).process(RESULT)
    assert any(r.message == "stage failed" for r in caplog.records)
