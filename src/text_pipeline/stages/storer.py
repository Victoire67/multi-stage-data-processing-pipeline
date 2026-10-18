"""Stage 3: persist analysis results through an injected repository."""

from __future__ import annotations

import logging

from text_pipeline.exceptions import StorageError
from text_pipeline.models import AnalysisResult, StoredRecord
from text_pipeline.repository import SentimentRepository
from text_pipeline.stages.base import PipelineStage

logger = logging.getLogger(__name__)


class DatabaseStorer(PipelineStage[AnalysisResult, StoredRecord]):
    """Store analysis results in a database.

    The storer's single responsibility is to be the pipeline-facing adapter
    for persistence: it validates its input, delegates to a
    :class:`~text_pipeline.repository.SentimentRepository`, logs and makes sure
    every failure surfaces as :class:`StorageError`. *Which* database is used is
    decided by the injected repository (PostgreSQL, in-memory, ...).
    """

    name = "storer"

    def __init__(self, repository: SentimentRepository) -> None:
        """Create the storer.

        Args:
            repository: Backend that actually persists the results.
        """
        self.repository = repository

    def process(self, data: AnalysisResult) -> StoredRecord:
        """Persist ``data``.

        Args:
            data: Output of the analysis stage.

        Returns:
            The stored record including its database id.

        Raises:
            StorageError: If the input is invalid or the backend fails.
        """
        logger.debug(
            "stage started",
            extra={"stage": self.name, "event": "stage_started"},
        )
        try:
            record = self._store(data)
        except StorageError as error:
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
                "state": record.to_log_dict(),
            },
        )
        return record

    def _store(self, data: object) -> StoredRecord:
        """Validate ``data`` and delegate to the repository."""
        if not isinstance(data, AnalysisResult):
            raise StorageError(f"expected AnalysisResult, got {type(data).__name__}")
        try:
            return self.repository.save(data)
        except StorageError:
            raise
        except Exception as error:  # defensive: backend-specific failures
            raise StorageError(f"unexpected error while storing: {error}") from error
