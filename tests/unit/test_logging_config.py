"""Unit tests for structured logging."""

import io
import json
import logging

from text_pipeline.logging_config import bind_run_id, configure_logging, run_id_var


def _last_line(stream: io.StringIO) -> str:
    return stream.getvalue().strip().splitlines()[-1]


def test_json_logs_include_extras_and_run_id() -> None:
    """JSON lines carry level, message, run_id and the extra fields."""
    stream = io.StringIO()
    configure_logging("DEBUG", stream=stream)
    logger = logging.getLogger("text_pipeline.test")

    with bind_run_id("run-42"):
        logger.info("stage completed", extra={"stage": "cleaner", "state": {"n": 1}})

    entry = json.loads(_last_line(stream))
    assert entry["level"] == "INFO"
    assert entry["message"] == "stage completed"
    assert entry["run_id"] == "run-42"
    assert entry["stage"] == "cleaner"
    assert entry["state"] == {"n": 1}
    assert entry["logger"] == "text_pipeline.test"


def test_run_id_is_reset_after_block() -> None:
    """The correlation id only applies inside bind_run_id."""
    with bind_run_id("inner"):
        assert run_id_var.get() == "inner"
    assert run_id_var.get() == "-"


def test_exceptions_are_serialised() -> None:
    """Tracebacks are included when logging with exc_info."""
    stream = io.StringIO()
    configure_logging(stream=stream)
    logger = logging.getLogger("text_pipeline.test")

    try:
        raise ValueError("bad value")
    except ValueError:
        logger.exception("failed")

    entry = json.loads(_last_line(stream))
    assert "ValueError: bad value" in entry["exception"]


def test_text_format_is_human_readable() -> None:
    """The text formatter shows run id, logger, message and extras."""
    stream = io.StringIO()
    configure_logging("INFO", json_format=False, stream=stream)
    logger = logging.getLogger("text_pipeline.test")

    with bind_run_id("abc"):
        logger.warning("careful", extra={"stage": "analyzer"})
        try:
            raise RuntimeError("x")
        except RuntimeError:
            logger.exception("oops")

    output = stream.getvalue()
    assert "[abc] text_pipeline.test: careful" in output
    assert '{"stage": "analyzer"}' in output
    assert "RuntimeError: x" in output


def test_reconfiguring_replaces_handler() -> None:
    """Calling configure_logging twice does not duplicate output."""
    configure_logging(stream=io.StringIO())
    logger = configure_logging(stream=io.StringIO())

    assert len(logger.handlers) == 1
    assert logger.propagate is False
