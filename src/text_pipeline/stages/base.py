"""The common interface implemented by every pipeline stage.

The pipeline only depends on this abstraction (Dependency Inversion), so any
stage can be swapped for another implementation, e.g. a different cleaner, a
real ML sentiment model, or a Redis storer, without touching the orchestrator
(Open/Closed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InT = TypeVar("InT", contravariant=True)
OutT = TypeVar("OutT", covariant=True)


class PipelineStage(ABC, Generic[InT, OutT]):
    """Abstract base class for a single, independently testable pipeline step.

    A stage receives the output of the previous stage, performs exactly one
    job (Single Responsibility) and returns a new immutable object for the next
    stage. On failure it must raise its own subclass of
    :class:`~text_pipeline.exceptions.PipelineError`.
    """

    #: Short, unique, human-readable stage name used in logs and errors.
    name: str = "stage"

    @abstractmethod
    def process(self, data: InT) -> OutT:
        """Transform ``data`` into the input of the next stage.

        Args:
            data: Output of the previous stage (or raw input for the first one).

        Returns:
            The transformed data.

        Raises:
            PipelineError: A stage-specific subclass when processing fails.
        """
