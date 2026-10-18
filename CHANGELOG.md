# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-19

### Added
- `PipelineStage` abstract base class (template method with structured logging).
- `TextCleaner`: unicode normalisation, HTML/URL stripping, punctuation removal
  that preserves in-word apostrophes, tokenisation, input validation.
- `SentimentAnalyzer`: simulated lexicon-based model with negation handling and
  an injectable `SentimentLexicon`.
- `DatabaseStorer` with `SentimentRepository` protocol, `PostgresSentimentRepository`
  (psycopg 3) and `InMemorySentimentRepository`.
- `TextProcessingPipeline` orchestrator with dependency injection, per-run
  correlation ids and batch processing; `build_pipeline()` composition root.
- Custom exceptions: `PipelineError`, `CleaningError`, `AnalysisError`, `StorageError`.
- Structured JSON logging (`logging_config`).
- `text-pipeline` CLI and `PIPELINE_*` environment configuration.
- Unit tests (pytest-mock) and integration tests (testcontainers + PostgreSQL 16),
  100% statement and branch coverage.
- Pre-commit hooks (Black, ruff, mypy), GitHub Actions CI, PR template.
- Debugging write-up (`docs/debugging.md`) with debugger transcript and log traces.

### Fixed
- Negation flipped every sentiment word in its window (`"not bad, it's great"`
  was neutral); it now flips only the first one.
- Intentionally introduced bug where the cleaner removed apostrophes, losing
  negators such as `don't` (see `docs/debugging.md`).
