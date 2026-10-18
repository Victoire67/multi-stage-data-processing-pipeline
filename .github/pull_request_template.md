## What does this PR do?

<!-- One or two sentences. Which pipeline stage / component is affected? -->

## How was it tested?

- [ ] Unit tests added/updated (`poetry run pytest tests/unit`)
- [ ] Integration tests pass (`poetry run pytest -m integration`, needs Docker)
- [ ] Coverage stays above the threshold (`poetry run pytest --cov`)

## Checklist

- [ ] `pre-commit` hooks pass (Black, ruff, mypy)
- [ ] Public classes/functions have docstrings
- [ ] New failures raise the stage's custom exception and are logged
- [ ] README/docs updated if behaviour changed
