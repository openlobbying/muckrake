# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Muckrake is the reusable FollowTheMoney data-pipeline core, published to PyPI. Application-specific code — the OpenLobbying crawlers, FastAPI app, Svelte frontend, FtM schema extensions, and deployment assets — lives in the sibling `../openlobbying/` repo, which depends on this repo as an editable path dependency. Nothing OpenLobbying-specific belongs here.

**Hard constraint 🔒:** muckrake must stay standalone and project-agnostic (it is the "data plane" in the muckrake × UTI merge — see `../docs/projects/undertheinfluence/merge-plan.md`). It must never import, reference, or know about Django, Popolo, Wagtail, or UTI; projections to consumer schemas live in consumer repos. Litmus test for every change: could a brand-new project use muckrake without pulling in any UTI/Django code?

## Current workstreams (July 2026)

Work in this repo is tracked on GitHub project boards 2 ("To-do", this repo's issues) and 3 ("muckrake × UTI merge", issues in `openlobbying/docs`). Merge-driven workstreams that land here:

- **Containerisation** ([docs#30](https://github.com/openlobbying/docs/issues/30), in progress): multi-stage Dockerfile + a standalone compose (Postgres with app + published DBs, CLI runner), with host ports chosen to avoid the UTI stack (db → 5433, API → 8001). The standalone compose must have no knowledge of UTI (🔒).
- **Tooling baseline + tests** (docs#33, #34): adopt ruff/mypy/pre-commit (currently none configured) and build out test coverage across core — existing tests only cover CLI entities, entity writes, and SQLite storage; load, release, artifacts, `make_id`, NER apply, and dedupe have essentially none. Hardening work should land with tests.
- **Workstream B — data-plane hardening** (docs#23–#29), prerequisite for UTI-scale ingestion (155k actors); fixes belong in core so all crawlers inherit them:
  - resilient fetch layer in `src/muckrake/extract/fetch.py`: retry + exponential backoff + rate limit + timeout (currently bare `raise_for_status()`)
  - crawl checkpointing + keep partial artifacts (`src/muckrake/crawl.py` currently discards everything on failure)
  - stream spreadsheet/CSV rows to the statement writer instead of materialising whole sheets
  - remove silent pagination caps; emit completeness warnings into the run summary
  - batched/incremental xref (hard `--limit 50000` today) + document complexity at 150k+ entities
  - atomic load in `src/muckrake/load.py` (currently delete-all-then-insert; a midway failure leaves the dataset empty)
  - opt-in concurrency for I/O-bound fetches
- **Phase 4 ports (later)**: Companies House enrichment stage feeding the resolver (+ seed UTI's 51k match decisions as judgements), and APPC-archive / ParlParse historical crawlers — generic GB data-plane capabilities, not UTI glue.
- A generic, project-agnostic export interface (docs#6) is an **open decision** that gates the merge's projection work — don't preempt its shape in code.

## Common commands

Always run Python via `uv` (never `python`/`python3`/`pip` directly).

- `uv sync` — install deps.
- `uv run muckrake --help` — full CLI reference.
- `uv run pytest` — run tests. Single test: `uv run pytest tests/test_foo.py::test_bar`.
- `docker compose up -d db` — optional local Postgres 18 on host port **5433** (offset so the undertheinfluence umbrella stack can hold 5432/8000); an init script creates the `muckrake` + `muckrake_published` databases. Without `MUCKRAKE_DATABASE_URL`, muckrake defaults to SQLite at `data/muckrake.db` (no setup needed).
- `docker compose run --rm muckrake <command>` — the containerised CLI (image installs muckrake non-editable; the repo is bind-mounted at `/work`, the runner's working directory, so datasets/data/.env come from the host). The image is also consumed by the undertheinfluence umbrella compose, which builds it from this checkout and points the runner's working directory at the openlobbying checkout instead.

Dataset configs are discovered from `./datasets/` in the **current working directory** plus `MUCKRAKE_DATASET_PATHS`. This repo ships no datasets — to run pipeline commands (`crawl`, `load`, `xref`, `dedupe`, `ner-extract`, `release-build`/`release-publish`, …) against real data, run them from `../openlobbying/`. The API server is also there (`uv run openlobbying server`); there is no `muckrake server` command.

## Architecture

Pipeline stages, in order, with on-disk/DB handoffs between them:

1. **Crawl** (`src/muckrake/crawl.py`, `dataset.py`) — runs a dataset's `crawl(dataset)` function, records a `dataset_runs` row, writes an immutable artifact under `MUCKRAKE_ARTIFACT_PATH` (default `data/artifacts/`), and mirrors the latest success to `data/datasets/<name>/statements.pack.csv`.
2. **NER extract/review** (`src/muckrake/extract/ner/`, see its README) — splits composite text fields into FtM fragment candidates (`delimiter` or `llm` extractor) stored in `ner_candidates`; only `approved` candidates are applied at load time.
3. **Load** (`src/muckrake/load.py`) — reads `statements.pack.csv` (or a `--run-id` artifact), applies approved NER candidates, materialises entities/relationships into the working DB.
4. **Dedupe** (`src/muckrake/dedupe/`, see its README) — `xref` generates resolver suggestions via `nomenklatura`; `dedupe` is the review TUI; `dedupe-edges` collapses duplicate `Representation` edges. Resolver state lives in the DB.
5. **Release** (`src/muckrake/release.py`) — `release-build` snapshots dataset runs into an immutable release; `release-publish` writes it into `MUCKRAKE_PUBLISHED_DATABASE_URL` (the read-only serving DB consumers query). Never `load` directly into the published DB.

The CLI (`src/muckrake/cli.py`) also exposes manual entity CRUD — `add`, `get`, `search`, `update` — for the "documenting investigations" use case where users (or agents) build a graph one entity at a time.

### FollowTheMoney model bootstrap

`src/muckrake/__init__.py` runs `_configure_ftm_model_path()` at import time: if extension schema dirs exist (from `MUCKRAKE_FTM_SCHEMA_PATHS` or `./ftm_schema_ext/` in the cwd), it overlays their YAMLs onto the upstream `followthemoney` schema in a tempdir and sets `FTM_MODEL_PATH` so all subsequent FtM imports see the merged model. Anything that uses FtM **must import `muckrake` first** — this is why `tests/conftest.py` exists; don't skip it in scripts or notebooks. Schema extensions belong in consuming app repos, not here.

## Environment

`MUCKRAKE_DATABASE_URL` (working DB; SQLite default when unset), `MUCKRAKE_PUBLISHED_DATABASE_URL` (defaults to working DB URL — use a separate DB when testing releases), `MUCKRAKE_DATA_PATH` / `MUCKRAKE_ARTIFACT_PATH` / `MUCKRAKE_DATASET_PATHS` overrides, `OPENROUTER_API_KEY` + `LLM_MODEL` for LLM-based NER. `.env` is loaded from the repo root of the current working directory (`MUCKRAKE_ENV_FILE` overrides); see `.env.example`.

## Conventions

- Code style: simple and tidy. No speculative abstractions, no backwards-compat shims, no defensive handling of conditions that don't occur.
- Typed Python. Be conservative about adding dependencies.
- Prefer existing `followthemoney` / `nomenklatura` functions before writing new ones — chances are they exist. FtM schema/property reference: https://followthemoney.tech/explorer/
- Crawler code must crash loudly on ambiguous data — never emit a guessed value.
- Keep README.md / AGENTS.md accurate when changing behaviour.
- Don't commit, push, or open PRs unless asked. `gh` CLI is available for read-only GitHub interactions.
