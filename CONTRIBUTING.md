# Contributing to muckrake

Read the shared guide first: [openlobbying/docs CONTRIBUTING.md](https://github.com/openlobbying/docs/blob/main/CONTRIBUTING.md). It covers the repos, branching (`develop` → `main`), releases and environments.

## In this repo

- Branch from `develop` and open PRs into `develop`.
- Before pushing:
  - `uv run pytest`
  - `uv run ruff check .` and `uv run ruff format .`
  - `uv run mypy src/`
  - Run `uv run pre-commit install` once so ruff runs on every commit.
- New behaviour comes with tests in `tests/`. `tests/conftest.py` isolates data paths and uses SQLite, so no database is needed.
- PyPI releases: tag `vX.Y.Z` on `main` only, after bumping `version` in `pyproject.toml`. The `Publish` workflow does the rest.

## The one rule

🔒 **muckrake is project-agnostic.** No imports of, or references to, Django, Popolo, Wagtail, UTI or OpenLobbying. Project-specific crawlers, schemas and apps live in the consuming repo, e.g. `openlobbying`.
