# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Muckrake is the reusable FollowTheMoney data-pipeline core, published to PyPI. Application-specific code — the OpenLobbying crawlers, FastAPI app, Svelte frontend, FtM schema extensions, and deployment assets — lives in the sibling `../openlobbying/` repo, which depends on this repo as an editable path dependency. Nothing OpenLobbying-specific belongs here (one exception remains: [crawl special-cases a dataset named "meetings"](https://github.com/openlobbying/muckrake/issues/53)).

**Hard constraint 🔒:** muckrake must stay standalone and project-agnostic (it is the "data plane" in the muckrake × UTI merge — see `../docs/projects/undertheinfluence/merge-plan.md`). It must never import, reference, or know about Django, Popolo, Wagtail, or UTI; projections to consumer schemas live in consumer repos. Litmus test for every change: could a brand-new project use muckrake without pulling in any UTI/Django code?

## Status and planning

Status lives on the project board, not here: [muckrake × UTI merge (board 3)](https://github.com/orgs/openlobbying/projects/3) (this repo's backlog is board 2, "To-do"), and the merge plan at `../docs/projects/undertheinfluence/merge-plan.md`. Check those before starting merge-related work.

Durable guidance from the merge:

- Data-plane hardening fixes belong in muckrake core so every crawler inherits them, and land with tests.
- [Decision: generic, project-agnostic muckrake export interface](https://github.com/openlobbying/docs/issues/6) is open and gates the projection work — don't preempt its shape in code.
- `scripts/litmus.sh` (run in CI) enforces the 🔒 constraint; extend its whitelist only for mentions that carry no behaviour.

## Common commands

Always run Python via `uv` (never `python`/`python3`/`pip` directly).

- `uv sync` — install deps. It compiles PyICU and plyvel, so it needs ICU, pkg-config and LevelDB headers (macOS: `brew install icu4c pkg-config leveldb` and `PKG_CONFIG_PATH="$(brew --prefix icu4c)/lib/pkgconfig"`; Debian: `libicu-dev pkg-config libleveldb-dev`).
- `uv run muckrake --help` — full CLI reference.
- `uv run pytest` — run tests. Single test: `uv run pytest tests/test_foo.py::test_bar`. Postgres-only tests need `MUCKRAKE_TEST_POSTGRES_URL` (a throwaway DB; see CONTRIBUTING.md).
- `uv run python scripts/gen_docs.py` — regenerate `docs/cli.md` and `docs/env.md` after changing a command, option or env var (`ENV_VARS` in `settings.py`); `tests/test_docs_current.py` fails if they drift.
- `bash scripts/litmus.sh` — the 🔒 project-agnostic check.
- `docker compose up -d db` — optional local Postgres 18 on host port **5433** (offset so the undertheinfluence umbrella stack can hold 5432/8000); an init script creates the `muckrake` + `muckrake_published` databases. Without `MUCKRAKE_DATABASE_URL`, muckrake defaults to SQLite at `data/muckrake.db` (the CLI creates `data/`).
- `docker compose run --rm muckrake <command>` — the containerised CLI (image installs muckrake non-editable; the repo is bind-mounted at `/work`, the runner's working directory, so datasets/data/.env come from the host). The image is also consumed by the undertheinfluence umbrella compose, which builds it from this checkout and points the runner's working directory at the openlobbying checkout instead.

Dataset configs are discovered from `./datasets/` in the **current working directory** plus `MUCKRAKE_DATASET_PATHS`. This repo ships no datasets apart from the quickstart example (`MUCKRAKE_DATASET_PATHS=examples`, dataset `hello`) — to run pipeline commands (`crawl`, `load`, `xref`, `dedupe`, `ner-extract`, `release-build`/`release-publish`, …) against real data, run them from `../openlobbying/`. The API server is also there (`uv run openlobbying server`); there is no `muckrake server` command.

## Architecture

Pipeline stages, in order, with on-disk/DB handoffs between them:

1. **Crawl** (`src/muckrake/crawl.py`, `dataset.py`) — runs a dataset's `crawl(dataset)` function, records a `dataset_runs` row, writes an immutable artifact under `MUCKRAKE_ARTIFACT_PATH` (default `data/artifacts/`), and mirrors the latest successful or `partial` run to `data/datasets/<name>/statements.pack.csv`.
2. **NER extract/review** (`src/muckrake/extract/ner/`, see its README) — splits composite text fields into FtM fragment candidates (`delimiter` or `llm` extractor) stored in the working DB's `ner_candidates` table; only `approved` candidates are applied (by `load`, `xref` and `release-build`). `ner-export`/`ner-import` keep candidates outside the DB so paid LLM results aren't repeated.
3. **Load** (`src/muckrake/load.py`) — reads `statements.pack.csv` (or a `--run-id` artifact), applies approved NER candidates, materialises entities/relationships into the working DB.
4. **Dedupe** (`src/muckrake/dedupe/`, see its README) — `xref` generates resolver suggestions via `nomenklatura`; `dedupe` is the review TUI; `dedupe-edges` collapses duplicate `Representation` edges. Resolver state lives in the working DB. `xref`, `dedupe`, `dedupe-edges` and `export` load LevelDB (`plyvel`), which builds on macOS but fails on import — run them in the container; every other command runs natively.
5. **Release** (`src/muckrake/release.py`) — `release-build` snapshots dataset runs into an immutable release; `release-publish` copies the working resolver and then swaps the release's statements into `MUCKRAKE_PUBLISHED_DATABASE_URL` (the read-only serving DB consumers query), which must differ from the working DB. Never `load` directly into the published DB.

The CLI (`src/muckrake/cli.py`) also exposes manual entity CRUD — `add`, `get`, `search`, `update` — for the "documenting investigations" use case where users (or agents) build a graph one entity at a time.

### FollowTheMoney model bootstrap

`src/muckrake/__init__.py` runs `_configure_ftm_model_path()` at import time: if extension schema dirs exist (from `MUCKRAKE_FTM_SCHEMA_PATHS` or `./ftm_schema_ext/` in the cwd), it overlays their YAMLs onto the upstream `followthemoney` schema in a tempdir and sets `FTM_MODEL_PATH` so all subsequent FtM imports see the merged model. Anything that uses FtM **must import `muckrake` first** — this is why `tests/conftest.py` exists; don't skip it in scripts or notebooks. Schema extensions belong in consuming app repos, not here.

## Environment

`MUCKRAKE_DATABASE_URL` (working DB; SQLite default when unset), `MUCKRAKE_PUBLISHED_DATABASE_URL` (must be a separate DB: `release-publish` refuses to run when it equals the working DB URL, which is its default), `MUCKRAKE_DATA_PATH` / `MUCKRAKE_ARTIFACT_PATH` / `MUCKRAKE_DATASET_PATHS` overrides, `LLM_MODEL` plus `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY` for LLM-based NER (`LLM_MODEL` needs its provider prefix, `openrouter:` or `anthropic:`). The HTTP cache behind `fetch_text/json/html` is the working DB's `cache` table; only `fetch_resource` writes files (`data/datasets/<name>/resources/`). Full list: `docs/env.md` (generated). The nearest `.env` from the current working directory upward is loaded (`MUCKRAKE_ENV_FILE` overrides; skipped when `ENVIRONMENT=production`); see `.env.example`.

## Conventions

- Code style: simple and tidy. No speculative abstractions, no backwards-compat shims, no defensive handling of conditions that don't occur.
- Typed Python. Be conservative about adding dependencies.
- Prefer existing `followthemoney` / `nomenklatura` functions before writing new ones — chances are they exist. FtM schema/property reference: https://followthemoney.tech/explorer/schemata/
- Crawler code must crash loudly on ambiguous data — never emit a guessed value.
- Keep README.md / AGENTS.md accurate when changing behaviour.
- Don't commit, push, or open PRs unless asked. `gh` CLI is available for read-only GitHub interactions.
