"""The orchestrator that chains the stages together.

:class:`TextProcessingPipeline` knows *nothing* about how text is cleaned,
scored or stored. It receives the three stages through its constructor
(dependency injection), runs them in order, binds a correlation id for
logging and turns failures into well-typed exceptions.

:func:`build_pipeline` is the composition root that wires the default
implementations together.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from text_pipeline.exceptions import PipelineError
from text_pipeline.logging_config import bind_run_id
from text_pipeline.models import AnalysisResult, CleanedText, StoredRecord
from text_pipeline.repository import SentimentRepository
from text_pipeline.stages.analyzer import SentimentAnalyzer
from text_pipeline.stages.base import PipelineStage
from text_pipeline.stages.cleaner import TextCleaner
from text_pipeline.stages.storer import DatabaseStorer

logger = logging.getLogger(__name__)

InT = TypeVar("InT")
OutT = TypeVar("OutT")

_PREVIEW_CHARS = 80


@dataclass(frozen=True, slots=True)
class FailedItem:
    """An input that could not be processed during a batch run.

    Attributes:
        index: Position of the input in the batch.
        text: The raw input.
        error: The pipeline error that stopped it.
    """

    index: int
    text: str
    error: PipelineError


@dataclass(slots=True)
class BatchResult:
    """Outcome of :meth:`TextProcessingPipeline.run_batch`.

    Attributes:
        records: Successfully stored records, in input order.
        failures: Inputs that failed, with the reason.
    """

    records: list[StoredRecord] = field(default_factory=list)
    failures: list[FailedItem] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        """Number of inputs that were stored."""
        return len(self.records)

    @property
    def failed(self) -> int:
        """Number of inputs that failed."""
        return len(self.failures)


class TextProcessingPipeline:
    """Run raw text through the cleaner, analyzer and storer stages."""

    def __init__(
        self,
        cleaner: PipelineStage[str, CleanedText],
        analyzer: PipelineStage[CleanedText, AnalysisResult],
        storer: PipelineStage[AnalysisResult, StoredRecord],
    ) -> None:
        """Assemble the pipeline from injected stages.

        Args:
            cleaner: Stage turning raw text into :class:`CleanedText`.
            analyzer: Stage turning :class:`CleanedText` into an analysis.
            storer: Stage persisting the analysis.
        """
        self.cleaner = cleaner
        self.analyzer = analyzer
        self.storer = storer

    @property
    def stage_names(self) -> list[str]:
        """Names of the stages in execution order."""
        return [self.cleaner.name, self.analyzer.name, self.storer.name]

    def run(self, text: str, *, run_id: str | None = None) -> StoredRecord:
        """Process a single input end to end.

        Args:
            text: Raw input text.
            run_id: Optional correlation id; a random one is generated if
                omitted. It appears on every log line of this run.

        Returns:
            The stored record.

        Raises:
            PipelineError: A stage-specific subclass (``CleaningError``,
                ``AnalysisError`` or ``StorageError``) if any stage fails.
        """
        with bind_run_id(run_id or uuid.uuid4().hex[:12]):
            started = time.perf_counter()
            logger.info(
                "pipeline started",
                extra={
                    "event": "pipeline_started",
                    "stages": self.stage_names,
                    "input_preview": _preview(text),
                },
            )
            try:
                cleaned = self._run_stage(self.cleaner, text)
                analysed = self._run_stage(self.analyzer, cleaned)
                record = self._run_stage(self.storer, analysed)
            except PipelineError as error:
                logger.error(
                    "pipeline failed",
                    extra={
                        "event": "pipeline_failed",
                        "failed_stage": error.stage,
                        "error_type": type(error).__name__,
                        "error": error.message,
                    },
                )
                raise
            logger.info(
                "pipeline completed",
                extra={
                    "event": "pipeline_completed",
                    "duration_ms": _elapsed_ms(started),
                    "state": record.to_log_dict(),
                },
            )
            return record

    def run_batch(self, texts: Iterable[str]) -> BatchResult:
        """Process many inputs, continuing past individual failures.

        Args:
            texts: Raw inputs.

        Returns:
            The stored records and the failures.
        """
        batch = BatchResult()
        for index, text in enumerate(texts):
            try:
                batch.records.append(self.run(text))
            except PipelineError as error:
                batch.failures.append(FailedItem(index, text, error))
        logger.info(
            "batch completed",
            extra={
                "event": "batch_completed",
                "succeeded": batch.succeeded,
                "failed": batch.failed,
            },
        )
        return batch

    @staticmethod
    def _run_stage(stage: PipelineStage[InT, OutT], data: InT) -> OutT:
        """Run one stage, timing it and normalising unexpected exceptions.

        Args:
            stage: The stage to run.
            data: Its input.

        Returns:
            The stage output.

        Raises:
            PipelineError: The stage's own error, or a generic ``PipelineError``
                if a (third-party) stage raised something else.
        """
        started = time.perf_counter()
        try:
            output = stage.process(data)
        except PipelineError:
            raise
        except Exception as error:
            raise PipelineError(
                f"stage {stage.name!r} raised unexpected "
                f"{type(error).__name__}: {error}"
            ) from error
        logger.debug(
            "stage timing",
            extra={"stage": stage.name, "duration_ms": _elapsed_ms(started)},
        )
        return output


def build_pipeline(
    repository: SentimentRepository,
    *,
    cleaner: PipelineStage[str, CleanedText] | None = None,
    analyzer: PipelineStage[CleanedText, AnalysisResult] | None = None,
) -> TextProcessingPipeline:
    """Wire the default stages together (composition root).

    Args:
        repository: Storage backend for the storer stage.
        cleaner: Optional replacement for the default :class:`TextCleaner`.
        analyzer: Optional replacement for the default
            :class:`SentimentAnalyzer`.

    Returns:
        A ready-to-use pipeline.
    """
    return TextProcessingPipeline(
        cleaner=cleaner or TextCleaner(),
        analyzer=analyzer or SentimentAnalyzer(),
        storer=DatabaseStorer(repository),
    )


def _preview(text: Any) -> str:
    """Return a short, single-line preview of ``text`` for logs."""
    value = str(text).replace("\n", " ")
    return value if len(value) <= _PREVIEW_CHARS else value[:_PREVIEW_CHARS] + "..."


def _elapsed_ms(started: float) -> float:
    """Milliseconds elapsed since ``started`` (a ``perf_counter`` value)."""
    return round((time.perf_counter() - started) * 1000, 3)
