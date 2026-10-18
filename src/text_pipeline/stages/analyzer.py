"""Stage 2: score the sentiment of cleaned text (simulated, lexicon based)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from text_pipeline.exceptions import AnalysisError
from text_pipeline.lexicon import DEFAULT_LEXICON, SentimentLexicon
from text_pipeline.models import AnalysisResult, CleanedText, Sentiment
from text_pipeline.stages.base import PipelineStage

logger = logging.getLogger(__name__)


class SentimentAnalyzer(PipelineStage[CleanedText, AnalysisResult]):
    """Classify cleaned text as positive, negative or neutral.

    This is a deliberately simple *simulated* model:

    * every token found in the positive/negative word list is a "hit";
    * a negator (``not``, ``don't``, ...) flips the polarity of hits within the
      next ``negation_window`` tokens;
    * ``score = (positive_hits - negative_hits) / (positive_hits + negative_hits)``
      (``0.0`` when there are no hits), so it always lies in ``[-1, 1]``;
    * ``|score| <= neutral_threshold`` is neutral, otherwise the sign decides.

    Because the analyzer implements :class:`PipelineStage`, it can be replaced
    by a real ML model without changing the rest of the pipeline.
    """

    name = "analyzer"

    def __init__(
        self,
        lexicon: SentimentLexicon | None = None,
        *,
        neutral_threshold: float = 0.1,
        negation_window: int = 3,
    ) -> None:
        """Configure the analyzer.

        Args:
            lexicon: Vocabulary to score with; defaults to ``DEFAULT_LEXICON``.
            neutral_threshold: Scores whose absolute value is at most this are
                neutral. Must be in ``[0, 1)``.
            negation_window: How many tokens after a negator are flipped.
                Must be at least 1.

        Raises:
            ValueError: If a setting is out of range.
        """
        if not 0.0 <= neutral_threshold < 1.0:
            raise ValueError("neutral_threshold must be in the range [0, 1)")
        if negation_window < 1:
            raise ValueError("negation_window must be at least 1")
        self.lexicon = lexicon or DEFAULT_LEXICON
        self.neutral_threshold = neutral_threshold
        self.negation_window = negation_window

    def process(self, data: CleanedText) -> AnalysisResult:
        """Analyse ``data``.

        Args:
            data: Output of the cleaning stage.

        Returns:
            The sentiment label, score and hit counts.

        Raises:
            AnalysisError: If the input is invalid or scoring fails.
        """
        logger.debug(
            "stage started",
            extra={"stage": self.name, "event": "stage_started"},
        )
        try:
            result = self._analyse(data)
        except AnalysisError as error:
            logger.warning(
                "stage failed",
                extra={
                    "stage": self.name,
                    "event": "stage_failed",
                    "error": str(error),
                },
            )
            raise
        logger.info(
            "stage completed",
            extra={
                "stage": self.name,
                "event": "stage_completed",
                "state": result.to_log_dict(),
            },
        )
        return result

    def _analyse(self, data: object) -> AnalysisResult:
        """Validate the input and build the analysis result."""
        if not isinstance(data, CleanedText):
            raise AnalysisError(f"expected CleanedText, got {type(data).__name__}")
        if not data.tokens:
            raise AnalysisError("cleaned text contains no tokens to analyse")

        try:
            positive, negative = self._count_hits(data.tokens)
            score = self._score(positive, negative)
        except Exception as error:  # defensive: never leak a raw exception
            raise AnalysisError(f"unexpected error while scoring: {error}") from error

        return AnalysisResult(
            original=data.original,
            cleaned=data.cleaned,
            sentiment=self._label(score),
            score=score,
            positive_hits=positive,
            negative_hits=negative,
        )

    def _count_hits(self, tokens: Sequence[str]) -> tuple[int, int]:
        """Count positive and negative hits, honouring negation.

        Args:
            tokens: The tokens to inspect.

        Returns:
            A ``(positive_hits, negative_hits)`` tuple.
        """
        positive = negative = 0
        negation_left = 0  # tokens still affected by the last negator
        for token in tokens:
            if token in self.lexicon.negators:
                negation_left = self.negation_window
                continue

            negated = negation_left > 0
            if token in self.lexicon.positive:
                if negated:
                    negative += 1
                else:
                    positive += 1
            elif token in self.lexicon.negative:
                if negated:
                    positive += 1
                else:
                    negative += 1

            if negation_left > 0:
                negation_left -= 1
        return positive, negative

    @staticmethod
    def _score(positive: int, negative: int) -> float:
        """Return the polarity score in ``[-1, 1]`` rounded to 4 decimals."""
        total = positive + negative
        if total == 0:
            return 0.0
        return round((positive - negative) / total, 4)

    def _label(self, score: float) -> Sentiment:
        """Map a score to a sentiment label using the neutral threshold."""
        if score > self.neutral_threshold:
            return Sentiment.POSITIVE
        if score < -self.neutral_threshold:
            return Sentiment.NEGATIVE
        return Sentiment.NEUTRAL
