# Contributing to muckrake

Set up a development environment with the
[README's installation steps](README.md#installation), then `uv sync` installs
the development tools too.

## Branches and pull requests

- `develop` is the default branch, where work is integrated. Branch from it and
  open pull requests into `develop`.
- `main` holds released versions only. It is protected and changes only through
  pull requests.
- A release is a pull request from `develop` into `main`, merged with a merge
  commit (not squashed), so `main` keeps the history of `develop`.
- A hotfix branches from `main`, is merged into `main` by pull request, and is
  then merged back into `develop`.

## Before you push

- `uv run pytest`
- `uv run ruff check .` and `uv run ruff format .`
- `uv run mypy src/`
- `bash scripts/litmus.sh` (see [project-agnostic code](#project-agnostic-code))
- Run `uv run pre-commit install` once so ruff runs on every commit.

CI runs all of these on every pull request, plus a link check over the Markdown
files.

## Tests

New behaviour comes with tests in `tests/`. `tests/conftest.py` points muckrake at
throwaway SQLite databases and data directories, so the suite needs no database
and never touches your `data/`.

A few tests exercise Postgres-only code (the `COPY`-and-swap publish). They are
skipped unless `MUCKRAKE_TEST_POSTGRES_URL` points at a **throwaway** database,
because they drop and recreate tables in it. With the compose database from the
README:

```bash
docker compose up -d db
docker compose exec db createdb -U muckrake muckrake_test
MUCKRAKE_TEST_POSTGRES_URL=postgresql://muckrake:muckrake@localhost:5433/muckrake_test uv run pytest
```

## Generated docs

[docs/cli.md](docs/cli.md) and [docs/env.md](docs/env.md) are generated from the
code. After changing a command, an option or an environment variable (variables
are listed in `ENV_VARS` in `src/muckrake/settings.py`), run:

```bash
uv run python scripts/gen_docs.py
```

`tests/test_docs_current.py` fails when the committed files are out of date, or
when the code reads an environment variable that `ENV_VARS` doesn't list.

## Releases

Releases go to PyPI from tags on `main` only:

1. On `develop`, bump `version` in `pyproject.toml` and move the `Unreleased`
   entries in `CHANGELOG.md` under the new version.
2. Merge `develop` into `main` (a release pull request, merge commit).
3. Tag the merge commit on `main` as `vX.Y.Z` and push the tag. The `Publish`
   workflow tests and uploads the package.

## Project-agnostic code

muckrake must not import or reference Django, Popolo, Wagtail or any specific
consuming application in `src/`, `tests/` or its dependencies. Project-specific
crawlers, schemas and apps live in the consuming repository.

`scripts/litmus.sh` checks for consumer project names in CI; its whitelist
explains the few allowed mentions (such as the GitHub organisation name in the
User-Agent). It only matches names, so it doesn't catch other project-specific
code: `crawl` still special-cases a dataset named `meetings`
([crawl special-cases a dataset named "meetings"](https://github.com/openlobbying/muckrake/issues/53)).
