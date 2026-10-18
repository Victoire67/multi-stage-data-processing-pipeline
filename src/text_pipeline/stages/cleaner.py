"""Stage 1: normalise raw text so it can be analysed reliably."""

from __future__ import annotations

import html
import re
import unicodedata

from text_pipeline.exceptions import CleaningError
from text_pipeline.models import CleanedText
from text_pipeline.stages.base import PipelineStage

_HTML_TAG = re.compile(r"<[^>]+>")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Anything that is not a letter/digit, whitespace or an apostrophe. Apostrophes
# must survive cleaning: the analyzer relies on negators such as "don't".
_NON_WORD = re.compile(r"[^\w\s']|_")
_WHITESPACE = re.compile(r"\s+")


class TextCleaner(PipelineStage[str, CleanedText]):
    """Turn raw user text into normalised, tokenised text.

    Cleaning steps, in order:

    1. Unicode NFKC normalisation (e.g. full-width letters become ASCII).
    2. Unescape HTML entities and strip HTML tags.
    3. Remove URLs.
    4. Optionally lower-case.
    5. Replace punctuation/symbols with spaces (apostrophes inside words such as
       ``don't`` are kept because the analyzer uses them for negation).
    6. Collapse whitespace and split into tokens.

    The cleaner has a single responsibility: it never scores or stores text.
    """

    name = "cleaner"
    error_type = CleaningError

    def __init__(self, *, lowercase: bool = True, max_length: int = 10_000) -> None:
        """Configure the cleaner.

        Args:
            lowercase: Lower-case the text when ``True``.
            max_length: Maximum accepted raw input length, in characters.

        Raises:
            ValueError: If ``max_length`` is not positive.
        """
        if max_length <= 0:
            raise ValueError("max_length must be a positive integer")
        self.lowercase = lowercase
        self.max_length = max_length

    def transform(self, data: str) -> CleanedText:
        """Clean ``data``.

        Args:
            data: Raw input text.

        Returns:
            The cleaned and tokenised text.

        Raises:
            CleaningError: If the input is not a string, is empty, is too long
                or contains nothing meaningful after cleaning.
        """
        if not isinstance(data, str):
            raise CleaningError(f"expected str, got {type(data).__name__}")
        if not data.strip():
            raise CleaningError("input text is empty")
        if len(data) > self.max_length:
            raise CleaningError(
                f"input of {len(data)} characters exceeds maximum length "
                f"of {self.max_length}"
            )

        text = unicodedata.normalize("NFKC", data)
        text = html.unescape(text)
        text = _HTML_TAG.sub(" ", text)
        text = _URL.sub(" ", text)
        if self.lowercase:
            text = text.lower()
        text = _NON_WORD.sub(" ", text)

        tokens = tuple(
            token.strip("'") for token in _WHITESPACE.split(text) if token.strip("'")
        )
        if not tokens:
            raise CleaningError("no meaningful content left after cleaning")

        return CleanedText(original=data, cleaned=" ".join(tokens), tokens=tokens)
