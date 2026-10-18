"""text_pipeline: a multi-stage text processing pipeline.

Raw text is cleaned, analysed for (simulated) sentiment and stored in a
database. Every stage is an independent, swappable component.
"""

from text_pipeline.exceptions import (
    AnalysisError,
    CleaningError,
    PipelineError,
    StorageError,
)
from text_pipeline.models import AnalysisResult, CleanedText, Sentiment, StoredRecord

__all__ = [
    "AnalysisError",
    "AnalysisResult",
    "CleanedText",
    "CleaningError",
    "PipelineError",
    "Sentiment",
    "StorageError",
    "StoredRecord",
]

__version__ = "1.0.0"
