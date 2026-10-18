"""Immutable data objects that flow between pipeline stages.

Each stage consumes the output type of the previous stage::

    str --TextCleaner--> CleanedText --SentimentAnalyzer--> AnalysisResult
        --DatabaseStorer--> StoredRecord

Using small frozen dataclasses (instead of dicts) gives us type checking with
mypy, self-documenting contracts between stages, and safe sharing because
nothing can be mutated after a stage hands it over.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Sentiment(StrEnum):
    """Possible sentiment labels produced by the analyzer."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class CleanedText:
    """Output of the cleaning stage.

    Attributes:
        original: The raw text exactly as it entered the pipeline.
        cleaned: Normalised text (lower-cased, markup/URLs removed, ...).
        tokens: The cleaned text split into word tokens.
    """

    original: str
    cleaned: str
    tokens: tuple[str, ...]

    def to_log_dict(self) -> dict[str, Any]:
        """Return a compact, log-friendly representation of this object."""
        return {
            "cleaned": self.cleaned,
            "token_count": len(self.tokens),
        }


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Output of the sentiment analysis stage.

    Attributes:
        original: The raw input text.
        cleaned: The cleaned text the analysis was performed on.
        sentiment: The resulting sentiment label.
        score: Polarity score in the closed range ``[-1.0, 1.0]``.
        positive_hits: Number of tokens counted as positive.
        negative_hits: Number of tokens counted as negative.
    """

    original: str
    cleaned: str
    sentiment: Sentiment
    score: float
    positive_hits: int
    negative_hits: int

    def to_log_dict(self) -> dict[str, Any]:
        """Return a compact, log-friendly representation of this object."""
        return {
            "sentiment": self.sentiment.value,
            "score": self.score,
            "positive_hits": self.positive_hits,
            "negative_hits": self.negative_hits,
        }


@dataclass(frozen=True, slots=True)
class StoredRecord:
    """Output of the storage stage: an analysis result plus persistence data.

    Attributes:
        id: Primary key assigned by the storage backend.
        original: The raw input text.
        cleaned: The cleaned text.
        sentiment: The sentiment label.
        score: The polarity score.
        positive_hits: Number of positive tokens.
        negative_hits: Number of negative tokens.
        created_at: Timestamp at which the record was stored.
    """

    id: int
    original: str
    cleaned: str
    sentiment: Sentiment
    score: float
    positive_hits: int
    negative_hits: int
    created_at: datetime

    def to_log_dict(self) -> dict[str, Any]:
        """Return a compact, log-friendly representation of this object."""
        return {"id": self.id, "sentiment": self.sentiment.value, "score": self.score}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary of all fields."""
        data = asdict(self)
        data["sentiment"] = self.sentiment.value
        data["created_at"] = self.created_at.isoformat()
        return data
