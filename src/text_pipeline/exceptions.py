"""Custom exception hierarchy for the text processing pipeline.

Every pipeline stage raises its *own* exception type so that callers (and log
readers) can tell immediately which stage failed. All of them derive from
:class:`PipelineError`, which lets the orchestrator catch "any pipeline
failure" with a single ``except`` clause while still preserving the specific
type.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for every error raised by the pipeline.

    Attributes:
        stage: Name of the stage that raised the error (``"pipeline"`` when the
            error is not attributable to a single stage).
        message: Human-readable description of the failure.
    """

    stage: str = "pipeline"

    def __init__(self, message: str) -> None:
        """Create the error.

        Args:
            message: Human-readable description of the failure.
        """
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        """Return the message prefixed with the failing stage name."""
        return f"[{self.stage}] {self.message}"


class CleaningError(PipelineError):
    """Raised by :class:`~text_pipeline.stages.cleaner.TextCleaner`.

    Examples: input is not a string, input is empty, input is too long, or
    nothing meaningful is left after cleaning.
    """

    stage = "cleaner"


class AnalysisError(PipelineError):
    """Raised by :class:`~text_pipeline.stages.analyzer.SentimentAnalyzer`.

    Examples: the analyzer received an unexpected payload type or a cleaned
    text without any tokens.
    """

    stage = "analyzer"


class StorageError(PipelineError):
    """Raised by the storage layer (storer stage and repositories).

    Examples: the database is unreachable, a constraint is violated, or the
    storer received an unexpected payload type.
    """

    stage = "storer"
