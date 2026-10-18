"""Word lists used by the (simulated) lexicon-based sentiment analyzer.

The vocabulary is kept apart from the scoring algorithm so it can be replaced,
e.g. with a finance or healthcare vocabulary, without touching the analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SentimentLexicon:
    """Vocabulary the analyzer uses to score tokens.

    Attributes:
        positive: Words that express a positive sentiment.
        negative: Words that express a negative sentiment.
        negators: Words that flip the polarity of the following words.
    """

    positive: frozenset[str]
    negative: frozenset[str]
    negators: frozenset[str]


_POSITIVE_WORDS = """
    amazing awesome beautiful best brilliant delight delighted delightful
    easy enjoy enjoyed excellent fantastic fast favorite fine friendly glad
    good great happy helpful impressive incredible like liked love loved
    lovely nice perfect pleasant recommend reliable satisfied smooth super
    superb thank thanks useful well wonderful worth
"""

_NEGATIVE_WORDS = """
    angry annoying awful bad boring broken buggy complaint confusing crash
    crashed defective disappointed disappointing dislike expensive fail
    failed frustrating hate hated horrible poor problem refund rude sad slow
    terrible ugly unhappy unreliable useless waste worse worst wrong
"""

_NEGATOR_WORDS = """
    aren't can't cannot didn't doesn't don't hardly isn't neither never no
    nor not nothing wasn't without won't wouldn't
"""

#: Lexicon used when no custom vocabulary is injected into the analyzer.
DEFAULT_LEXICON = SentimentLexicon(
    positive=frozenset(_POSITIVE_WORDS.split()),
    negative=frozenset(_NEGATIVE_WORDS.split()),
    negators=frozenset(_NEGATOR_WORDS.split()),
)
