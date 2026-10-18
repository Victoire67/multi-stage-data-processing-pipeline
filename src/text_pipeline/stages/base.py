"""The common interface implemented by every pipeline stage.

The pipeline only depends on this abstraction (Dependency Inversion), so any
stage can be swapped for another implementation, e.g. a different cleaner, a
real ML sentiment model, or a Redis storer, without touching the orchestrator
(Open/Closed).

:meth:`PipelineStage.process` is a *template method*: it owns the
cross-cutting concerns that every stage needs (structured logging of the
start, the resulting state and failures), while subclasses only implement the
actual transformation in :meth:`PipelineStage.transform`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, Protocol, TypeVar, runtime_checkable

from text_pipeline.exceptions import PipelineError

InT = TypeVar("InT", contravariant=True)
OutT = TypeVar("OutT", covariant=True)


@runtime_checkable
class SupportsLogDict(Protocol):
    """An object that can describe itself compactly for structured logs."""

    def to_log_dict(self) -> dict[str, Any]:
        """Return a small JSON-serialisable summary."""
        ...


class PipelineStage(ABC, Generic[InT, OutT]):
    """Abstract base class for a single, independently testable pipeline step.

    A stage receives the output of the previous stage, performs exactly one
    job (Single Responsibility) and returns a new immutable object for the next
    stage. On failure it must raise its own subclass of
    :class:`~text_pipeline.exceptions.PipelineError` (``error_type``).
    """

    #: Short, unique, human-readable stage name used in logs and errors.
    name: ClassVar[str] = "stage"

    #: The stage-specific exception raised by :meth:`transform`.
    error_type: ClassVar[type[PipelineError]] = PipelineError

    def process(self, data: InT) -> OutT:
        """Run the stage on ``data`` with structured logging.

        Logs ``stage started`` (DEBUG), then either ``stage completed`` (INFO)
        with the resulting state, or ``stage failed`` (WARNING) before
        re-raising the stage error.

        Args:
            data: Output of the previous stage (or raw input for the first one).

        Returns:
            The transformed data.

        Raises:
            PipelineError: The stage-specific subclass when processing fails.
        """
        stage_logger = logging.getLogger(type(self).__module__)
        stage_logger.debug(
            "stage started",
            extra={"stage": self.name, "event": "stage_started"},
        )
        try:
            result = self.transform(data)
        except PipelineError as error:
            stage_logger.warning(
                "stage failed",
                extra={
                    "stage": self.name,
                    "event": "stage_failed",
                    "error_type": type(error).__name__,
                    "error": error.message,
                },
            )
            raise
        stage_logger.info(
            "stage completed",
            extra={
                "stage": self.name,
                "event": "stage_completed",
                "state": _describe(result),
            },
        )
        return result

    @abstractmethod
    def transform(self, data: InT) -> OutT:
        """Do the stage's actual work (no logging needed here).

        Args:
            data: Output of the previous stage.

        Returns:
            The transformed data.

        Raises:
            PipelineError: The stage's ``error_type`` when processing fails.
        """


def _describe(result: object) -> dict[str, Any]:
    """Return a log-friendly summary of a stage result."""
    if isinstance(result, SupportsLogDict):
        return result.to_log_dict()
    return {"type": type(result).__name__}
