# Multi-Stage Data Processing Pipeline

[![CI](https://github.com/Victoire67/multi-stage-data-processing-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Victoire67/multi-stage-data-processing-pipeline/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000)

A Python pipeline that takes **raw text**, **cleans** it, **analyses its
sentiment** (simulated, lexicon based) and **stores** the structured result in
**PostgreSQL**. Each stage is a separate, swappable component you can test on
its own. The project is built around SOLID design, a testing pyramid (unit
tests with `pytest-mock`, integration tests with `testcontainers-python`),
structured logging, and a Git Flow workflow guarded by pre-commit hooks.

---

## Table of contents

1. [Architecture](#architecture)
2. [Project structure](#project-structure)
3. [Getting started](#getting-started)
4. [Usage](#usage)
5. [Testing & coverage](#testing--coverage)
6. [Logging & error handling](#logging--error-handling)
7. [Debugging](#debugging)
8. [Code quality & Git workflow](#code-quality--git-workflow)

---

## Architecture

```mermaid
flowchart LR
    IN([raw text]) --> P

    subgraph P[TextProcessingPipeline - orchestrator]
        direction LR
        C[TextCleaner<br/><i>stage 1</i>] -->|CleanedText| A[SentimentAnalyzer<br/><i>stage 2</i>]
        A -->|AnalysisResult| S[DatabaseStorer<br/><i>stage 3</i>]
    end

    S -->|save| R{{SentimentRepository<br/>protocol}}
    R -.implements.- PG[(PostgresSentimentRepository<br/>PostgreSQL)]
    R -.implements.- MEM[(InMemorySentimentRepository)]
    S -->|StoredRecord| OUT([stored record])

    L[[lexicon.SentimentLexicon]] -. injected .-> A
    LOG[[logging_config<br/>JSON logs + run_id]] -. observes .-> P
```

```
 raw text ──► TextCleaner ──CleanedText──► SentimentAnalyzer ──AnalysisResult──► DatabaseStorer ──► StoredRecord
                  │                              │                                     │
            CleaningError                  AnalysisError                         StorageError
                  └──────────────────────────────┴───────────── all subclass PipelineError

 DatabaseStorer ──depends on──► SentimentRepository (Protocol)
                                   ├── PostgresSentimentRepository  (psycopg 3, production)
                                   └── InMemorySentimentRepository  (demos / fast tests)
```

### How a request flows

1. `TextProcessingPipeline.run(text)` binds a **correlation id** (`run_id`) and
   logs `pipeline started`.
2. Each stage's `process()` (a *template method* in `PipelineStage`) logs
   `stage started`, calls the stage's `transform()`, then logs
   `stage completed` with the **new state**, or `stage failed`.
3. The output of every stage is an **immutable dataclass** that becomes the
   input of the next stage.
4. `DatabaseStorer` hands the result to the injected repository; PostgreSQL
   assigns an `id` and `created_at`.
5. On any failure, the stage-specific exception propagates and the pipeline
   logs `pipeline failed` with the failing stage.

### SOLID in practice

| Principle | Where |
|---|---|
| **S**ingle Responsibility | `TextCleaner` only cleans, `SentimentAnalyzer` only scores, `DatabaseStorer` only adapts persistence for the pipeline, `PostgresSentimentRepository` only talks SQL, `logging_config` only formats logs. |
| **O**pen/Closed | New stages, lexicons or storage backends are added by implementing an interface; the orchestrator never changes (see `tests/unit/test_base_stage.py`). |
| **L**iskov Substitution | Any `PipelineStage[In, Out]` or `SentimentRepository` can replace the default one (mocks, in-memory, PostgreSQL). |
| **I**nterface Segregation | Stages expose one method (`process`/`transform`); the repository protocol has only `save`, `get`, `list_all`. |
| **D**ependency Inversion | The pipeline depends on the `PipelineStage` ABC; the storer depends on the `SentimentRepository` protocol; everything is wired in one composition root, `build_pipeline()`. |

### The simulated sentiment model

* Tokens found in the positive/negative word lists count as hits.
* A negator (`not`, `don't`, `never`, ...) flips the **first** sentiment word
  within the next 3 tokens (`"not bad"` → positive; `"not bad, it's great"`
  → positive).
* `score = (pos - neg) / (pos + neg)` ∈ [-1, 1]; `|score| ≤ 0.1` → neutral.

---

## Project structure

```
multi-stage-data-processing-pipeline/
├── src/text_pipeline/
│   ├── __init__.py          # public API re-exports
│   ├── __main__.py          # `python -m text_pipeline`
│   ├── cli.py               # command-line interface
│   ├── config.py            # settings from PIPELINE_* env vars
│   ├── exceptions.py        # PipelineError, CleaningError, AnalysisError, StorageError
│   ├── lexicon.py           # sentiment word lists (injectable)
│   ├── logging_config.py    # JSON/text formatter, run_id correlation
│   ├── models.py            # CleanedText, AnalysisResult, StoredRecord, Sentiment
│   ├── pipeline.py          # TextProcessingPipeline + build_pipeline()
│   ├── repository.py        # SentimentRepository protocol, PostgreSQL & in-memory
│   └── stages/
│       ├── base.py          # PipelineStage ABC (template method)
│       ├── cleaner.py       # TextCleaner
│       ├── analyzer.py      # SentimentAnalyzer
│       └── storer.py        # DatabaseStorer
├── tests/
│   ├── unit/                # isolated tests, dependencies mocked with pytest-mock
│   └── integration/         # real PostgreSQL via testcontainers-python
├── docs/
│   ├── debugging.md         # debugging session write-up
│   ├── debugging/           # pdb transcript, failing tests, log traces
│   └── coverage/            # coverage report (text + HTML)
├── scripts/debug_session.py # reproduces the debugged bug
├── examples/reviews.txt     # sample input
├── .github/                 # CI workflow + PR template
├── .vscode/launch.json      # debugger configurations
├── .pre-commit-config.yaml  # Black, ruff, mypy, hygiene hooks
├── docker-compose.yml       # local PostgreSQL for manual runs
├── pyproject.toml           # Poetry project + tool configuration
├── poetry.lock
└── requirements.txt         # pip alternative (includes testcontainers)
```

---

## Getting started

**Requirements:** Python 3.11+, [Poetry](https://python-poetry.org/) 2.x and
Docker (only for integration tests and the PostgreSQL backend).

```bash
git clone https://github.com/Victoire67/multi-stage-data-processing-pipeline.git
cd multi-stage-data-processing-pipeline
poetry install                    # creates .venv and installs everything
poetry run pre-commit install     # enable the git hooks
```

<details>
<summary>Without Poetry (pip)</summary>

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e . --no-deps
```
</details>

---

## Usage

### Command line

```bash
# No database needed
poetry run text-pipeline --in-memory "I love it" "This is terrible"

# Read one input per line, human-readable logs
poetry run text-pipeline --in-memory --file examples/reviews.txt --log-format text

# PostgreSQL
docker compose up -d
export PIPELINE_DATABASE_URL=postgresql://pipeline:pipeline@localhost:5432/pipeline
poetry run text-pipeline --file examples/reviews.txt
```

Stored records go to **stdout** as JSON lines; logs go to **stderr**. The exit
code is `0` when everything was stored, `1` if some inputs failed, and `2`
for usage errors.

```json
{"id": 4, "original": "I don't love it, honestly.", "cleaned": "i don't love it honestly", "sentiment": "negative", "score": -1.0, "positive_hits": 0, "negative_hits": 1, "created_at": "..."}
```

| Environment variable | Meaning | Default |
|---|---|---|
| `PIPELINE_DATABASE_URL` | PostgreSQL DSN | *(unset)* |
| `PIPELINE_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `PIPELINE_LOG_FORMAT` | `json` / `text` | `json` |

### As a library

```python
from text_pipeline.logging_config import configure_logging
from text_pipeline.pipeline import build_pipeline
from text_pipeline.repository import PostgresSentimentRepository
from text_pipeline.stages.analyzer import SentimentAnalyzer

configure_logging("INFO")
repo = PostgresSentimentRepository("postgresql://pipeline:pipeline@localhost/pipeline")
repo.initialize_schema()

pipeline = build_pipeline(repo, analyzer=SentimentAnalyzer(neutral_threshold=0.3))
record = pipeline.run("Not bad at all!")
batch = pipeline.run_batch(["great", "", "awful"])   # continues past failures
print(record.sentiment, batch.succeeded, batch.failed)
```

---

## Testing & coverage

```bash
poetry run pytest                          # everything (Docker needed for integration)
poetry run pytest tests/unit               # fast unit tests only
poetry run pytest -m integration           # testcontainers + PostgreSQL only
poetry run pytest --cov --cov-report=html  # coverage (fails under 90%)
```

| Layer | What | How |
|---|---|---|
| **Unit** (120 tests) | each stage, repository, pipeline, CLI, logging, config in isolation | `pytest-mock` mocks stages, the repository and the psycopg connection |
| **Integration** (10 tests) | full pipeline → real PostgreSQL 16, verified with direct SQL; constraint violations; connection failures; CLI end to end; log correlation across stages | `testcontainers-python` starts `postgres:16-alpine` once per session; skipped automatically if Docker is unavailable |

**Coverage: 100% of statements and branches** (512 statements, 82 branches).
The report is in [`docs/coverage/coverage_report.txt`](docs/coverage/coverage_report.txt)
and the browsable HTML version is in `docs/coverage/html/index.html`.

---

## Logging & error handling

Every log line is JSON and carries the `run_id` of the input being processed,
so one item can be followed through all stages:

```json
{"level": "INFO", "logger": "text_pipeline.pipeline", "message": "pipeline started", "run_id": "5ceb7cb40bd7", "stages": ["cleaner", "analyzer", "storer"], "input_preview": "I don't love it"}
{"level": "INFO", "logger": "text_pipeline.stages.cleaner", "message": "stage completed", "run_id": "5ceb7cb40bd7", "stage": "cleaner", "state": {"cleaned": "i don't love it", "token_count": 4}}
{"level": "INFO", "logger": "text_pipeline.stages.analyzer", "message": "stage completed", "run_id": "5ceb7cb40bd7", "stage": "analyzer", "state": {"sentiment": "negative", "score": -1.0, "positive_hits": 0, "negative_hits": 1}}
{"level": "INFO", "logger": "text_pipeline.stages.storer", "message": "stage completed", "run_id": "5ceb7cb40bd7", "stage": "storer", "state": {"id": 1, "sentiment": "negative", "score": -1.0}}
{"level": "INFO", "logger": "text_pipeline.pipeline", "message": "pipeline completed", "run_id": "5ceb7cb40bd7", "duration_ms": 0.41, "state": {"id": 1, "sentiment": "negative", "score": -1.0}}
```

| Exception | Raised by | Typical causes |
|---|---|---|
| `CleaningError` | `TextCleaner` | not a string, empty, longer than `max_length`, nothing left after cleaning |
| `AnalysisError` | `SentimentAnalyzer` | wrong input type, no tokens, unexpected scoring failure (wrapped) |
| `StorageError` | `DatabaseStorer`, repositories | DB unreachable, constraint violation, wrong input type, driver errors (wrapped) |
| `PipelineError` | base class / orchestrator | a third-party stage raised a non-pipeline exception (wrapped) |

The original exception is always kept as `__cause__`.

---

## Debugging

A bug was **introduced on purpose** (the cleaner dropped apostrophes, so
`"I don't love it"` was stored as *positive*) and tracked down with
breakpoints, watch expressions and call-stack inspection. The full write-up,
with the debugger transcript and before/after log traces, is in
**[docs/debugging.md](docs/debugging.md)**. VS Code launch configurations are
in [`.vscode/launch.json`](.vscode/launch.json).

---

## Code quality & Git workflow

* **Black** (formatting), **ruff** (lint, import order, pydocstyle with Google
  docstrings), **mypy --strict** (typing). All three run in **pre-commit** and
  in **GitHub Actions** (Python 3.11 / 3.12 / 3.13).
* **Git Flow:** `main` (releases) ← `develop` (integration) ← one branch per
  feature or pipeline stage, merged with `--no-ff` so every feature stays
  visible in history:

| Branch | Content |
|---|---|
| `feature/project-setup` | Poetry, tooling, pre-commit, core interfaces/models/exceptions |
| `feature/structured-logging` | JSON logging + `run_id` correlation |
| `feature/text-cleaner` | tests first, then `TextCleaner` |
| `feature/sentiment-analyzer` | tests first, then lexicon + `SentimentAnalyzer` |
| `feature/database-storer` | tests first, then repositories + `DatabaseStorer` |
| `feature/pipeline-orchestrator` | orchestrator, config, CLI |
| `feature/integration-tests` | testcontainers integration suite |
| `chore/ci-and-requirements` | CI, PR template, requirements.txt, VS Code configs |
| `bugfix/negation-lost-in-cleaner` | intentional bug → debugging → fix |
| `refactor/stage-template-method` | logging moved into `PipelineStage.process` |
| `docs/readme-and-coverage` | this README, coverage report, examples |
| `release/1.0.0` | version bump, merged into `main` and tagged `v1.0.0` |

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `ci:`, `chore:`).
