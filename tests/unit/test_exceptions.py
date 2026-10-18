"""Unit tests for the custom exception hierarchy."""

import pytest

from text_pipeline.exceptions import (
    AnalysisError,
    CleaningError,
    PipelineError,
    StorageError,
)


@pytest.mark.parametrize(
    ("error_type", "stage"),
    [
        (CleaningError, "cleaner"),
        (AnalysisError, "analyzer"),
        (StorageError, "storer"),
    ],
)
def test_stage_errors_carry_stage_name_and_inherit_base(
    error_type: type[PipelineError], stage: str
) -> None:
    """Each stage error is a PipelineError tagged with its stage name."""
    error = error_type("boom")

    assert isinstance(error, PipelineError)
    assert error.stage == stage
    assert error.message == "boom"
    assert str(error) == f"[{stage}] boom"


def test_base_error_defaults_to_pipeline_stage() -> None:
    """The base error is attributed to the pipeline as a whole."""
    assert str(PipelineError("bad")) == "[pipeline] bad"
