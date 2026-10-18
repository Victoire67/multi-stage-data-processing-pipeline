"""Unit tests for the TextCleaner stage (written before the implementation)."""

import logging

import pytest

from text_pipeline.exceptions import CleaningError
from text_pipeline.models import CleanedText
from text_pipeline.stages.base import PipelineStage
from text_pipeline.stages.cleaner import TextCleaner


@pytest.fixture
def cleaner() -> TextCleaner:
    """Return a cleaner with default settings."""
    return TextCleaner()


def test_is_a_pipeline_stage(cleaner: TextCleaner) -> None:
    """The cleaner implements the common stage interface."""
    assert isinstance(cleaner, PipelineStage)
    assert cleaner.name == "cleaner"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello World", "hello world"),
        ("  lots   of\n\tspaces  ", "lots of spaces"),
        ("<p>I <b>love</b> it</p>", "i love it"),
        ("Visit https://example.com/x?y=1 now", "visit now"),
        ("see www.example.org today", "see today"),
        ("Great!!! Really??? #wow", "great really wow"),
        ("Fish &amp; chips", "fish chips"),
        ("I don't like it", "i don't like it"),
        ("'quoted' words", "quoted words"),
        ("Ｆｕｌｌｗｉｄｔｈ text", "fullwidth text"),
        ("snake_case_word", "snake case word"),
        ("Café déjà vu", "café déjà vu"),
    ],
)
def test_normalises_text(cleaner: TextCleaner, raw: str, expected: str) -> None:
    """Markup, URLs, punctuation and extra whitespace are removed."""
    result = cleaner.process(raw)

    assert result.cleaned == expected
    assert result.original == raw
    assert result.tokens == tuple(expected.split())


def test_returns_cleaned_text_model(cleaner: TextCleaner) -> None:
    """The stage output is the CleanedText contract for the next stage."""
    assert isinstance(cleaner.process("ok"), CleanedText)


def test_lowercasing_can_be_disabled() -> None:
    """Case is preserved when lowercase=False."""
    assert TextCleaner(lowercase=False).process("Hello World").cleaned == "Hello World"


@pytest.mark.parametrize("bad_input", [None, 42, b"bytes", ["list"]])
def test_rejects_non_string_input(cleaner: TextCleaner, bad_input: object) -> None:
    """Non-string payloads raise CleaningError."""
    with pytest.raises(CleaningError, match="expected str"):
        cleaner.process(bad_input)  # type: ignore[arg-type]


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_rejects_empty_input(cleaner: TextCleaner, blank: str) -> None:
    """Blank input raises CleaningError."""
    with pytest.raises(CleaningError, match="empty"):
        cleaner.process(blank)


def test_rejects_input_without_meaningful_content(cleaner: TextCleaner) -> None:
    """Input that is only punctuation/markup/URLs leaves nothing to analyse."""
    with pytest.raises(CleaningError, match="no meaningful content"):
        cleaner.process("<br/> !!! https://example.com ???")


def test_rejects_too_long_input() -> None:
    """Input longer than max_length raises CleaningError."""
    with pytest.raises(CleaningError, match="exceeds maximum length"):
        TextCleaner(max_length=5).process("too long text")


def test_invalid_configuration_is_rejected() -> None:
    """max_length must be positive."""
    with pytest.raises(ValueError, match="max_length"):
        TextCleaner(max_length=0)


def test_logs_state_after_stage(
    cleaner: TextCleaner, caplog: pytest.LogCaptureFixture
) -> None:
    """A structured 'stage completed' record with the new state is emitted."""
    with caplog.at_level(logging.DEBUG, logger="text_pipeline"):
        cleaner.process("Nice day")

    completed = [r for r in caplog.records if r.message == "stage completed"]
    assert len(completed) == 1
    record = completed[0]
    assert record.stage == "cleaner"  # type: ignore[attr-defined]
    assert record.state == {  # type: ignore[attr-defined]
        "cleaned": "nice day",
        "token_count": 2,
    }


def test_logs_failure(cleaner: TextCleaner, caplog: pytest.LogCaptureFixture) -> None:
    """Failures are logged at WARNING level with the stage name."""
    with caplog.at_level(logging.WARNING, logger="text_pipeline"):
        with pytest.raises(CleaningError):
            cleaner.process("")

    assert any(r.message == "stage failed" for r in caplog.records)
