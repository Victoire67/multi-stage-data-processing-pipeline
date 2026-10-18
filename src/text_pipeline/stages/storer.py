"""Stage 3: persist analysis results through an injected repository."""

from __future__ import annotations

from text_pipeline.exceptions import StorageError
from text_pipeline.models import AnalysisResult, StoredRecord
from text_pipeline.repository import SentimentRepository
from text_pipeline.stages.base import PipelineStage


class DatabaseStorer(PipelineStage[AnalysisResult, StoredRecord]):
    """Store analysis results in a database.

    The storer's single responsibility is to be the pipeline-facing adapter
    for persistence: it validates its input, delegates to a
    :class:`~text_pipeline.repository.SentimentRepository`, logs and makes sure
    every failure surfaces as :class:`StorageError`. *Which* database is used is
    decided by the injected repository (PostgreSQL, in-memory, ...).
    """

    name = "storer"
    error_type = StorageError

    def __init__(self, repository: SentimentRepository) -> None:
        """Create the storer.

        Args:
            repository: Backend that actually persists the results.
        """
        self.repository = repository

    def transform(self, data: AnalysisResult) -> StoredRecord:
        """Persist ``data``.

        Args:
            data: Output of the analysis stage.

        Returns:
            The stored record including its database id.

        Raises:
            StorageError: If the input is invalid or the backend fails.
        """
        if not isinstance(data, AnalysisResult):
            raise StorageError(f"expected AnalysisResult, got {type(data).__name__}")
        try:
            return self.repository.save(data)
        except StorageError:
            raise
        except Exception as error:  # defensive: backend-specific failures
            raise StorageError(f"unexpected error while storing: {error}") from error
