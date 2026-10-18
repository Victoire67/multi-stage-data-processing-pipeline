"""Unit tests for the PipelineStage template method and stage swapping."""

import logging

import pytest

from text_pipeline.exceptions import CleaningError, PipelineError
from text_pipeline.models import CleanedText
from text_pipeline.pipeline import build_pipeline
from text_pipeline.repository import InMemorySentimentRepository
from text_pipeline.stages.base import PipelineStage


class WordCountStage(PipelineStage[str, int]):
    """Minimal custom stage whose result has no ``to_log_dict``."""

    name = "word-count"

    def transform(self, data: str) -> int:
        """Count words."""
        return len(data.split())


class KeepOnlyLettersCleaner(PipelineStage[str, CleanedText]):
    """A drop-in replacement cleaner used to prove stages are swappable."""

    name = "letters-cleaner"
    error_type = CleaningError

    def transform(self, data: str) -> CleanedText:
        """Keep alphabetic words only, without lower-casing."""
        tokens = tuple(word for word in data.split() if word.isalpha())
        if not tokens:
            raise CleaningError("nothing left")
        return CleanedText(data, " ".join(tokens), tokens)


def test_process_logs_generic_state_for_plain_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Results without to_log_dict are summarised by their type name."""
    with caplog.at_level(logging.DEBUG, logger="tests"):
        assert WordCountStage().process("a b c") == 3

    completed = next(r for r in caplog.records if r.message == "stage completed")
    assert completed.state == {"type": "int"}  # type: ignore[attr-defined]
    assert completed.stage == "word-count"  # type: ignore[attr-defined]


def test_abstract_stage_cannot_be_instantiated() -> None:
    """transform() must be implemented by concrete stages."""
    with pytest.raises(TypeError):
        PipelineStage()  # type: ignore[abstract]


def test_default_error_type_is_pipeline_error() -> None:
    """Stages that do not override error_type use the base error."""
    assert WordCountStage.error_type is PipelineError


def test_custom_stage_can_replace_default_cleaner() -> None:
    """Open/Closed: a new cleaner is injected without touching the pipeline."""
    pipeline = build_pipeline(
        InMemorySentimentRepository(), cleaner=KeepOnlyLettersCleaner()
    )

    record = pipeline.run("great 123 product")

    assert record.cleaned == "great product"
    assert pipeline.stage_names[0] == "letters-cleaner"
