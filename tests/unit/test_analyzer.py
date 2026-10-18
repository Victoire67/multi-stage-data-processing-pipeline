"""Unit tests for the SentimentAnalyzer stage (written before the implementation)."""

import logging

import pytest
from pytest_mock import MockerFixture

from text_pipeline.exceptions import AnalysisError
from text_pipeline.lexicon import DEFAULT_LEXICON, SentimentLexicon
from text_pipeline.models import AnalysisResult, CleanedText, Sentiment
from text_pipeline.stages.analyzer import SentimentAnalyzer
from text_pipeline.stages.base import PipelineStage


def make_cleaned(text: str) -> CleanedText:
    """Build the analyzer input directly, without depending on TextCleaner."""
    return CleanedText(original=text, cleaned=text, tokens=tuple(text.split()))


@pytest.fixture
def analyzer() -> SentimentAnalyzer:
    """Return an analyzer with the default lexicon."""
    return SentimentAnalyzer()


def test_is_a_pipeline_stage(analyzer: SentimentAnalyzer) -> None:
    """The analyzer implements the common stage interface."""
    assert isinstance(analyzer, PipelineStage)
    assert analyzer.name == "analyzer"


@pytest.mark.parametrize(
    ("text", "sentiment", "score"),
    [
        ("i love this great product", Sentiment.POSITIVE, 1.0),
        ("this is terrible and awful", Sentiment.NEGATIVE, -1.0),
        ("the package arrived on tuesday", Sentiment.NEUTRAL, 0.0),
        ("good but bad", Sentiment.NEUTRAL, 0.0),
        ("good great but bad", Sentiment.POSITIVE, 0.3333),
    ],
)
def test_scores_polarity(
    analyzer: SentimentAnalyzer, text: str, sentiment: Sentiment, score: float
) -> None:
    """Score is (pos - neg) / (pos + neg) and drives the label."""
    result = analyzer.process(make_cleaned(text))

    assert result.sentiment is sentiment
    assert result.score == pytest.approx(score, abs=1e-4)


@pytest.mark.parametrize(
    ("text", "sentiment"),
    [
        ("not good", Sentiment.NEGATIVE),
        ("this is not bad", Sentiment.POSITIVE),
        ("i don't love it", Sentiment.NEGATIVE),
        ("never happy with it", Sentiment.NEGATIVE),
    ],
)
def test_negation_flips_polarity(
    analyzer: SentimentAnalyzer, text: str, sentiment: Sentiment
) -> None:
    """A negator flips the polarity of the sentiment word that follows it."""
    assert analyzer.process(make_cleaned(text)).sentiment is sentiment


def test_negation_only_applies_within_window(analyzer: SentimentAnalyzer) -> None:
    """Negation fades after `negation_window` tokens.

    "not bad" is positive; "great" comes 5 tokens later and must stay positive.
    """
    result = analyzer.process(make_cleaned("not bad and the service was great"))

    assert result.positive_hits == 2
    assert result.negative_hits == 0
    assert result.sentiment is Sentiment.POSITIVE


def test_negation_flips_only_the_first_sentiment_word(
    analyzer: SentimentAnalyzer,
) -> None:
    """Regression: in "not bad it's great" only "bad" is negated."""
    result = analyzer.process(make_cleaned("not bad it's great"))

    assert (result.positive_hits, result.negative_hits) == (2, 0)
    assert result.sentiment is Sentiment.POSITIVE


def test_counts_hits(analyzer: SentimentAnalyzer) -> None:
    """Positive and negative hits are reported for observability."""
    result = analyzer.process(make_cleaned("good excellent horrible"))

    assert (result.positive_hits, result.negative_hits) == (2, 1)


def test_result_carries_text_forward(analyzer: SentimentAnalyzer) -> None:
    """The original and cleaned text are passed on to the storer."""
    cleaned = CleanedText("Great!", "great", ("great",))
    result = analyzer.process(cleaned)

    assert isinstance(result, AnalysisResult)
    assert (result.original, result.cleaned) == ("Great!", "great")


def test_neutral_threshold_is_configurable() -> None:
    """A higher threshold classifies weak polarity as neutral."""
    text = make_cleaned("good great but bad")  # score 0.3333
    assert SentimentAnalyzer(neutral_threshold=0.5).process(text).sentiment is (
        Sentiment.NEUTRAL
    )


def test_custom_lexicon_can_be_injected() -> None:
    """The lexicon is a dependency, so domain vocabularies can be swapped in."""
    lexicon = SentimentLexicon(
        positive=frozenset({"bullish"}),
        negative=frozenset({"bearish"}),
        negators=frozenset({"not"}),
    )
    analyzer = SentimentAnalyzer(lexicon=lexicon)

    assert analyzer.process(make_cleaned("very bullish")).sentiment is (
        Sentiment.POSITIVE
    )
    assert analyzer.process(make_cleaned("great")).sentiment is Sentiment.NEUTRAL


def test_default_lexicon_has_no_overlap() -> None:
    """A word cannot be both positive and negative."""
    assert not DEFAULT_LEXICON.positive & DEFAULT_LEXICON.negative


@pytest.mark.parametrize(
    "kwargs",
    [{"neutral_threshold": -0.1}, {"neutral_threshold": 1.0}, {"negation_window": 0}],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    """Out-of-range settings raise ValueError."""
    with pytest.raises(ValueError, match="must be"):
        SentimentAnalyzer(**kwargs)  # type: ignore[arg-type]


def test_rejects_wrong_input_type(analyzer: SentimentAnalyzer) -> None:
    """A raw string (skipping the cleaner) is rejected."""
    with pytest.raises(AnalysisError, match="expected CleanedText"):
        analyzer.process("raw text")  # type: ignore[arg-type]


def test_rejects_empty_tokens(analyzer: SentimentAnalyzer) -> None:
    """There is nothing to analyse without tokens."""
    with pytest.raises(AnalysisError, match="no tokens"):
        analyzer.process(CleanedText("x", "", ()))


def test_unexpected_errors_are_wrapped(
    analyzer: SentimentAnalyzer, mocker: MockerFixture
) -> None:
    """Any unexpected failure inside scoring surfaces as AnalysisError."""
    mocker.patch.object(analyzer, "_count_hits", side_effect=ZeroDivisionError("x"))

    with pytest.raises(AnalysisError, match="unexpected error") as excinfo:
        analyzer.process(make_cleaned("good"))
    assert isinstance(excinfo.value.__cause__, ZeroDivisionError)


def test_logs_state_after_stage(
    analyzer: SentimentAnalyzer, caplog: pytest.LogCaptureFixture
) -> None:
    """A structured 'stage completed' record with the new state is emitted."""
    with caplog.at_level(logging.INFO, logger="text_pipeline"):
        analyzer.process(make_cleaned("great"))

    record = next(r for r in caplog.records if r.message == "stage completed")
    assert record.stage == "analyzer"  # type: ignore[attr-defined]
    assert record.state["sentiment"] == "positive"  # type: ignore[attr-defined]


def test_logs_failure(
    analyzer: SentimentAnalyzer, caplog: pytest.LogCaptureFixture
) -> None:
    """Failures are logged with the stage name before being raised."""
    with (
        caplog.at_level(logging.WARNING, logger="text_pipeline"),
        pytest.raises(AnalysisError),
    ):
        analyzer.process(CleanedText("x", "", ()))

    assert any(r.message == "stage failed" for r in caplog.records)
