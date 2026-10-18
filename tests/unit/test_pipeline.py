"""Unit tests for the pipeline orchestrator (all stages are mocked)."""

import logging
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from text_pipeline.exceptions import (
    AnalysisError,
    CleaningError,
    PipelineError,
    StorageError,
)
from text_pipeline.models import AnalysisResult, CleanedText, Sentiment, StoredRecord
from text_pipeline.pipeline import TextProcessingPipeline, build_pipeline
from text_pipeline.repository import InMemorySentimentRepository
from text_pipeline.stages.analyzer import SentimentAnalyzer
from text_pipeline.stages.base import PipelineStage
from text_pipeline.stages.cleaner import TextCleaner
from text_pipeline.stages.storer import DatabaseStorer

CLEANED = CleanedText("Good!", "good", ("good",))
ANALYSED = AnalysisResult("Good!", "good", Sentiment.POSITIVE, 1.0, 1, 0)
RECORD = StoredRecord(
    1, "Good!", "good", Sentiment.POSITIVE, 1.0, 1, 0, datetime.now(tz=UTC)
)


def _stage(mocker: MockerFixture, name: str, output: object) -> Mock:
    stage = mocker.Mock(spec=PipelineStage)
    stage.name = name
    stage.process.return_value = output
    return stage  # type: ignore[no-any-return]


@pytest.fixture
def stages(mocker: MockerFixture) -> tuple[Mock, Mock, Mock]:
    """Three mocked stages returning canned outputs."""
    return (
        _stage(mocker, "cleaner", CLEANED),
        _stage(mocker, "analyzer", ANALYSED),
        _stage(mocker, "storer", RECORD),
    )


@pytest.fixture
def pipeline(stages: tuple[Mock, Mock, Mock]) -> TextProcessingPipeline:
    """A pipeline assembled from the mocked stages (dependency injection)."""
    return TextProcessingPipeline(*stages)


def test_runs_stages_in_order_passing_outputs_along(
    pipeline: TextProcessingPipeline, stages: tuple[Mock, Mock, Mock]
) -> None:
    """Each stage receives the previous stage's output."""
    cleaner, analyzer, storer = stages

    assert pipeline.run("Good!") is RECORD
    cleaner.process.assert_called_once_with("Good!")
    analyzer.process.assert_called_once_with(CLEANED)
    storer.process.assert_called_once_with(ANALYSED)
    assert pipeline.stage_names == ["cleaner", "analyzer", "storer"]


@pytest.mark.parametrize(
    ("failing_index", "error"),
    [
        (0, CleaningError("empty")),
        (1, AnalysisError("no tokens")),
        (2, StorageError("db down")),
    ],
)
def test_stage_error_stops_pipeline_and_propagates(
    pipeline: TextProcessingPipeline,
    stages: tuple[Mock, Mock, Mock],
    failing_index: int,
    error: PipelineError,
) -> None:
    """The specific stage error propagates and later stages never run."""
    stages[failing_index].process.side_effect = error

    with pytest.raises(type(error)) as excinfo:
        pipeline.run("x")

    assert excinfo.value is error
    for later in stages[failing_index + 1 :]:
        later.process.assert_not_called()


def test_unexpected_exception_from_custom_stage_is_wrapped(
    pipeline: TextProcessingPipeline, stages: tuple[Mock, Mock, Mock]
) -> None:
    """A third-party stage raising e.g. KeyError surfaces as PipelineError."""
    stages[1].process.side_effect = KeyError("boom")

    with pytest.raises(PipelineError, match="'analyzer' raised unexpected KeyError"):
        pipeline.run("x")


def test_logs_lifecycle_with_shared_run_id(
    pipeline: TextProcessingPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    """Start/complete events are logged and the run id is bound."""
    with caplog.at_level(logging.DEBUG, logger="text_pipeline"):
        pipeline.run("Good!", run_id="fixed-id")

    messages = [r.message for r in caplog.records]
    assert messages[0] == "pipeline started"
    assert messages[-1] == "pipeline completed"
    assert messages.count("stage timing") == 3


def test_logs_failure_with_failed_stage(
    pipeline: TextProcessingPipeline,
    stages: tuple[Mock, Mock, Mock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed run logs which stage failed."""
    stages[2].process.side_effect = StorageError("db down")

    with (
        caplog.at_level(logging.ERROR, logger="text_pipeline"),
        pytest.raises(StorageError),
    ):
        pipeline.run("x")

    record = next(r for r in caplog.records if r.message == "pipeline failed")
    assert record.failed_stage == "storer"  # type: ignore[attr-defined]
    assert record.error_type == "StorageError"  # type: ignore[attr-defined]


def test_long_input_is_truncated_in_logs(
    pipeline: TextProcessingPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    """Log previews stay short even for very long inputs."""
    with caplog.at_level(logging.INFO, logger="text_pipeline"):
        pipeline.run("word " * 100)

    record = next(r for r in caplog.records if r.message == "pipeline started")
    assert record.input_preview.endswith("...")  # type: ignore[attr-defined]
    assert len(record.input_preview) == 83  # type: ignore[attr-defined]


def test_run_batch_continues_after_failures(
    pipeline: TextProcessingPipeline, stages: tuple[Mock, Mock, Mock]
) -> None:
    """A failing input is reported while the others are still processed."""
    stages[0].process.side_effect = [CLEANED, CleaningError("empty"), CLEANED]

    batch = pipeline.run_batch(["a", "", "c"])

    assert batch.succeeded == 2
    assert batch.failed == 1
    assert batch.failures[0].index == 1
    assert isinstance(batch.failures[0].error, CleaningError)


def test_build_pipeline_wires_default_stages() -> None:
    """The composition root uses the default stage implementations."""
    repo = InMemorySentimentRepository()
    pipeline = build_pipeline(repo)

    assert isinstance(pipeline.cleaner, TextCleaner)
    assert isinstance(pipeline.analyzer, SentimentAnalyzer)
    assert isinstance(pipeline.storer, DatabaseStorer)
    assert pipeline.storer.repository is repo


def test_build_pipeline_allows_swapping_stages() -> None:
    """Custom stages can be injected without changing the orchestrator."""
    custom = SentimentAnalyzer(neutral_threshold=0.9)
    pipeline = build_pipeline(InMemorySentimentRepository(), analyzer=custom)

    assert pipeline.analyzer is custom


def test_end_to_end_with_real_stages_and_in_memory_storage() -> None:
    """Real stages + in-memory backend: a fast end-to-end smoke test."""
    repo = InMemorySentimentRepository()
    pipeline = build_pipeline(repo)

    record = pipeline.run("<p>This is NOT bad, it's great!</p>")

    assert record.cleaned == "this is not bad it's great"
    assert record.sentiment is Sentiment.POSITIVE
    assert repo.list_all() == [record]
