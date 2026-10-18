"""Reproduce the negation bug used in the debugging exercise.

Run it under a debugger, e.g.::

    poetry run python -m pdb scripts/debug_session.py

or with the "Python: Current File" configuration in VS Code. Expected output
is ``negative``; with the bug present it prints ``positive``.
"""

from text_pipeline.pipeline import build_pipeline
from text_pipeline.repository import InMemorySentimentRepository

TEXT = "I don't love it"


def main() -> None:
    """Run the pipeline on a single negated sentence and print the outcome."""
    pipeline = build_pipeline(InMemorySentimentRepository())
    record = pipeline.run(TEXT, run_id="debug-session")
    print(f"input={TEXT!r} cleaned={record.cleaned!r} sentiment={record.sentiment}")


if __name__ == "__main__":
    main()
