"""Command-line interface.

Examples::

    # Store in PostgreSQL (DSN from flag or PIPELINE_DATABASE_URL)
    text-pipeline --database-url postgresql://user:pw@localhost/db "I love it"

    # No database needed: keep results in memory, read one text per line
    text-pipeline --in-memory --file reviews.txt --log-format text

Each stored record is printed to stdout as one JSON line; logs go to stderr.
The exit code is ``0`` when every input was stored, ``1`` if at least one
failed and ``2`` for usage/configuration errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from text_pipeline import __version__
from text_pipeline.config import Settings
from text_pipeline.exceptions import StorageError
from text_pipeline.logging_config import configure_logging
from text_pipeline.pipeline import build_pipeline
from text_pipeline.repository import (
    InMemorySentimentRepository,
    PostgresSentimentRepository,
    SentimentRepository,
)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="text-pipeline",
        description="Clean text, analyse its sentiment and store the result.",
    )
    parser.add_argument("texts", nargs="*", help="texts to process")
    parser.add_argument(
        "-f", "--file", type=Path, help="read inputs from a file (one per line)"
    )
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument(
        "--database-url", help="PostgreSQL DSN (default: $PIPELINE_DATABASE_URL)"
    )
    backend.add_argument(
        "--in-memory", action="store_true", help="store results in memory only"
    )
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--log-format", choices=["json", "text"])
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _read_inputs(args: argparse.Namespace) -> list[str]:
    """Collect inputs from positional arguments and/or ``--file``."""
    texts: list[str] = list(args.texts)
    if args.file is not None:
        lines = args.file.read_text(encoding="utf-8").splitlines()
        texts.extend(line for line in lines if line.strip())
    return texts


def _make_repository(
    args: argparse.Namespace, settings: Settings
) -> SentimentRepository:
    """Choose the storage backend from the CLI flags and settings."""
    if args.in_memory:
        return InMemorySentimentRepository()
    dsn = args.database_url or settings.database_url
    if not dsn:
        raise ValueError(
            "no database configured: pass --database-url, set "
            "PIPELINE_DATABASE_URL or use --in-memory"
        )
    repository = PostgresSentimentRepository(dsn)
    repository.initialize_schema()
    return repository


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments (without the program name); defaults to ``sys.argv``.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        env = Settings.from_env()
        settings = Settings(
            database_url=env.database_url,
            log_level=(args.log_level or env.log_level).upper(),
            log_format=args.log_format or env.log_format,
        )
        texts = _read_inputs(args)
    except (ValueError, OSError) as error:
        parser.print_usage(sys.stderr)
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    if not texts:
        parser.print_usage(sys.stderr)
        print("error: no input text given", file=sys.stderr)
        return EXIT_USAGE

    configure_logging(settings.log_level, json_format=settings.log_format == "json")

    try:
        repository = _make_repository(args, settings)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except StorageError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILURES

    batch = build_pipeline(repository).run_batch(texts)
    for record in batch.records:
        print(json.dumps(record.to_dict(), ensure_ascii=False))
    for failure in batch.failures:
        print(f"failed input #{failure.index}: {failure.error}", file=sys.stderr)
    return EXIT_OK if batch.failed == 0 else EXIT_FAILURES
