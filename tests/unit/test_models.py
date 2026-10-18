"""Unit tests for the immutable data models passed between stages."""

import dataclasses
from datetime import UTC, datetime

import pytest

from text_pipeline.models import AnalysisResult, CleanedText, Sentiment, StoredRecord


def test_cleaned_text_is_frozen_and_logs_compactly() -> None:
    """CleanedText cannot be mutated and exposes a small log payload."""
    cleaned = CleanedText(original="Hi!", cleaned="hi", tokens=("hi",))

    with pytest.raises(dataclasses.FrozenInstanceError):
        cleaned.cleaned = "changed"  # type: ignore[misc]
    assert cleaned.to_log_dict() == {"cleaned": "hi", "token_count": 1}


def test_analysis_result_log_dict() -> None:
    """AnalysisResult logs the label as a plain string."""
    result = AnalysisResult("a", "a", Sentiment.POSITIVE, 1.0, 1, 0)

    assert result.to_log_dict() == {
        "sentiment": "positive",
        "score": 1.0,
        "positive_hits": 1,
        "negative_hits": 0,
    }


def test_stored_record_serialises_to_json_friendly_dict() -> None:
    """StoredRecord.to_dict converts enums and datetimes to strings."""
    created = datetime(2026, 1, 1, tzinfo=UTC)
    record = StoredRecord(7, "a", "a", Sentiment.NEGATIVE, -0.5, 0, 1, created)

    assert record.to_dict()["sentiment"] == "negative"
    assert record.to_dict()["created_at"] == "2026-01-01T00:00:00+00:00"
    assert record.to_log_dict() == {"id": 7, "sentiment": "negative", "score": -0.5}
