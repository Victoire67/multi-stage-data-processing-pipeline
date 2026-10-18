"""Structured (JSON) logging for the pipeline.

Every log line is a single JSON object, which makes it easy to follow one
piece of data as it moves through the stages: all lines produced while
processing the same input share a ``run_id`` (a correlation id stored in a
:class:`contextvars.ContextVar`, so stages never have to pass it around).

Stages attach their state through the standard ``extra`` argument::

    logger.info(
        "stage completed",
        extra={"stage": "cleaner", "event": "stage_completed", "state": {...}},
    )

which is rendered as::

    {"timestamp": "...", "level": "INFO", "logger": "text_pipeline.stages.cleaner",
     "message": "stage completed", "run_id": "3f2a...", "stage": "cleaner",
     "event": "stage_completed", "state": {...}}
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import IO, Any

#: Correlation id of the pipeline run currently being processed.
run_id_var: ContextVar[str] = ContextVar("run_id", default="-")

# Attributes present on every LogRecord; anything else came from ``extra``.
_RESERVED_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()
    | {"message", "asctime", "run_id", "taskName"}
)


class RunContextFilter(logging.Filter):
    """Inject the current ``run_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach ``run_id`` to ``record`` and always keep the record.

        Args:
            record: The record being logged.

        Returns:
            Always ``True``; this filter only enriches records.
        """
        record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise ``record`` (including any ``extra`` fields) to JSON.

        Args:
            record: The record to format.

        Returns:
            A JSON string without trailing newline.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", run_id_var.get()),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-friendly single-line formatter that still shows the extras."""

    def format(self, record: logging.LogRecord) -> str:
        """Format ``record`` as ``time level [run_id] logger: message {extras}``.

        Args:
            record: The record to format.

        Returns:
            The formatted line.
        """
        extras = {k: v for k, v in vars(record).items() if k not in _RESERVED_ATTRS}
        line = (
            f"{self.formatTime(record)} {record.levelname:<7} "
            f"[{getattr(record, 'run_id', '-')}] {record.name}: {record.getMessage()}"
        )
        if extras:
            line += " " + json.dumps(extras, default=str, ensure_ascii=False)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(
    level: int | str = logging.INFO,
    *,
    json_format: bool = True,
    stream: IO[str] | None = None,
) -> logging.Logger:
    """Configure the ``text_pipeline`` logger hierarchy.

    Calling it again replaces the previously installed handler, so it is safe
    to call from tests and from the CLI.

    Args:
        level: Minimum level to emit (e.g. ``"DEBUG"`` or ``logging.INFO``).
        json_format: Emit JSON lines when ``True``, readable text otherwise.
        stream: Where to write logs; defaults to ``sys.stderr``.

    Returns:
        The configured package logger.
    """
    logger = logging.getLogger("text_pipeline")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter() if json_format else TextFormatter())
    handler.addFilter(RunContextFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


@contextmanager
def bind_run_id(run_id: str) -> Iterator[str]:
    """Set the correlation id for all log lines emitted inside the block.

    Args:
        run_id: Identifier of the pipeline run.

    Yields:
        The bound ``run_id``.
    """
    token = run_id_var.set(run_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(token)
