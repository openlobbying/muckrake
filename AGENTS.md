## Good practices

Always use `uv` to run Python commands, never `python`, `python3` or `pip` directly.

Chances are a lot of the code you'll want to write is redundant and is already provided by [`followthemoney`](https://followthemoney.tech/docs/) and [`nomenklatura`](https://github.com/opensanctions/nomenklatura). Check the documentation and codebase to see if you can use existing functions before writing new ones.

Key Resources:
- FtM entity schemata: https://followthemoney.tech/explorer/schemata/
- FtM property types: https://followthemoney.tech/explorer/types/

Keep code simple and tidy. We don't need excessive abstractions and over-engineering. We don't need backwards compatibility. We don't need to account for edge cases before they arise.

Keep documentation up to date and accurate when you add new features or make changes.

Crawlers must crash loudly on uncertain data, never emit ambiguous information.

## Deployment conventions

- Production DB is configured via `MUCKRAKE_DATABASE_URL` (Postgres), local defaults to SQLite.
- Production publishing uses one curated DB artifact (must include resolver + ner_candidates state).
- Frontend calls backend through relative `/api/*` routes (no hardcoded localhost URLs).
- For local frontend dev, Vite proxies `/api` to `http://127.0.0.1:8000`.
- Deployment templates and VPS runbook live in `docs/deploy/`.
- Do not commit secrets or server-specific private values into repo files.

## Project Overview

Read [[muckrake/README]] for an overview of the project and common commands.

**Muckrake** is an ETL framework for tracking lobbying and political finance data using the FollowTheMoney (FtM) entity model. It crawls structured/semi-structured government data, performs entity deduplication, stores entities in LevelDB, and serves them via a FastAPI backend with a SvelteKit frontend.
