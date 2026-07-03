A framework for creating and storing [FollowTheMoney](https://followthemoney.tech/) entities, used by [OpenLobbying](https://openlobbying.org/).

> [!WARNING]
> This is a work in progress. Expect breaking changes and incomplete features.

## Muckrake

Muckrake is the data pipeline. It is partially inspired by [`zavod`](https://zavod.opensanctions.org/) and [other tools in the FollowTheMoney ecosystems](https://followthemoney.tech/community/stack/).

### Setup

The compose stack runs Postgres 18, the API, and pipeline commands in containers. Host ports are offset (db `5433`, API `8001`) so it can run side by side with the undertheinfluence stack.

```bash
# Postgres (creates the app + published databases) and the API on http://127.0.0.1:8001
docker compose up -d

# Full list of available commands (muckrake --help)
docker compose run --rm muckrake --help
```

The `muckrake` service's entrypoint is the muckrake CLI, so `docker compose run --rm muckrake <command>` is the container equivalent of `uv run muckrake <command>`. The repo is bind-mounted into the containers: code changes, `datasets/`, `data/` (fetch cache + artifacts) and the repo-root `.env` are shared with the host (the database URLs are overridden to point at the compose Postgres).

To work on the host instead, copy `.env.example` to `.env` (see [Environment setup](#environment-setup)), install dependencies with `uv sync`, start Postgres with `docker compose up -d db`, and run commands with `uv run muckrake <command>`.

Muckrake also extends the FollowTheMoney model with local `Meeting`, `Donation`, `Gift`, and `Hospitality` schemata. The package bootstrap configures `FTM_MODEL_PATH` automatically so crawls, loads, exports, releases, and the API all use the same model inside this repo.

### Crawlers

You can find crawlers for [various datasets](https://openlobbying.org/datasets) in `datasets/`. At a minimum, each dataset consists of a `config.yml` with metadata and a `crawl.py` script that outputs FollowTheMoney statements in CSV format.

To crawl a dataset, run `docker compose run --rm muckrake crawl {dataset_name}`. Run `docker compose run --rm muckrake list` to see available datasets.

Each crawl now creates a `dataset_runs` record in Postgres and stores immutable artifacts under `MUCKRAKE_ARTIFACT_PATH` (defaults to `data/artifacts`). The latest successful run remains mirrored into `data/datasets/{name}/statements.pack.csv` for local compatibility.

### AI-based NER

Many data sources have [composite fields that contain multiple entities](https://openaccess.transparency.org.uk/?meeting=10088). We use LLMs to extract unique entities and relationships from these fields, and store them as candidates in the database for review and approval. See [NER docs](/src/muckrake/extract/ner/README.md) for details.

LLM-based extraction needs `OPENROUTER_API_KEY` and `LLM_MODEL` in the repo-root `.env` — the containers pick these up through the bind mount.

```bash
# Create extraction candidates for one dataset
docker compose run --rm muckrake ner-extract open_access --extractor llm --limit 50

# Review candidates in a terminal UI
docker compose run --rm muckrake ner-review
```

### Dedupe

Our goal is to link entities across datasets to provide a unified view of lobbying and political finance for any given person, company, or organisation.

```bash
# Create dedupe candidates across all datasets
docker compose run --rm muckrake xref

# Review candidates in a terminal UI
docker compose run --rm muckrake dedupe
```

We also want to collapse duplicate relationship edges across datasets, especially for ORCL and PRCA. This is done automatically, no review step required.

```bash
docker compose run --rm muckrake dedupe-edges
```

### Loading

Statements are loaded into Postgres with `docker compose run --rm muckrake load`. This reads the statements CSV files and applies any approved NER candidates before materialising entities and relationships.

To load from a specific immutable crawl snapshot instead of the local workspace copy:

```bash
docker compose run --rm muckrake load gb_political_finance --run-id 123
```

For the published site, prefer the release workflow instead of loading directly into the serving database:

```bash
docker compose run --rm muckrake release-build
docker compose run --rm muckrake release-publish 1
```


## OpenLobbying

The primary user of Muckrake data is [OpenLobbying](https://openlobbying.org/), an open database of lobbying and political finance data.

The compose stack serves the API at `http://127.0.0.1:8001` (started by `docker compose up -d`). On the host, `uv run muckrake server` serves it at `http://127.0.0.1:8000`.

Start the Svelte frontend:

```bash
cd openlobbying
npm run dev
```

In development, frontend requests to `/api/*` are proxied to `http://127.0.0.1:8000` via Vite (override with `MUCKRAKE_API_URL`, e.g. `http://127.0.0.1:8001` for the containerised API).

## Environment setup

- Copy `.env.example` to `.env` in the repo root.
- That single repo-root `.env` is used for local Python and frontend development, and is shared with the containers via the bind mount. Docker-only use works without one (compose sets the database URLs), but LLM-based NER needs the `OPENROUTER_API_KEY`/`LLM_MODEL` values from it.
- Required for local development:
  - `MUCKRAKE_DATABASE_URL`
- Common local settings:
  - `MUCKRAKE_PUBLISHED_DATABASE_URL` for a separate published API database
  - `BETTER_AUTH_SECRET` for a stable local auth secret. If omitted, development falls back to a fixed local secret.
  - `BETTER_AUTH_URL`, usually `http://localhost:5173`
- Optional local overrides:
  - `MUCKRAKE_API_URL`
  - `MUCKRAKE_DATA_PATH`
  - `MUCKRAKE_ARTIFACT_PATH`
  - `FTM_MODEL_PATH` if you need to override the repo's merged local FollowTheMoney model
  - `OPENROUTER_API_KEY`, `LLM_MODEL`, `NER_LLM_PROMPT_FILE`, `LOGFIRE_TOKEN`
- Example:

```bash
cp .env.example .env
```

## Deployment docs

- Deployment runbook: `ops/README.md`
- App deployment assets: `ops/`
- One-command app deploy: `./ops/deploy_to_vps.sh {ip_address}`
