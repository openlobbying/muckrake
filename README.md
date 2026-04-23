A framework for creating and storing [FollowTheMoney](https://followthemoney.tech/) entities, used by [OpenLobbying](https://openlobbying.org/).

> [!WARNING]
> This is a work in progress. Expect breaking changes and incomplete features.

## Muckrake

Muckrake is the data pipeline. It is partially inspired by [`zavod`](https://zavod.opensanctions.org/) and [other tools in the FollowTheMoney ecosystems](https://followthemoney.tech/community/stack/).

Run `uv run muckrake --help` for a full list of available commands.

Install Python dependencies with `uv sync`. This now includes the external `org-id` package used for structured organization identifiers.

### Crawlers

You can find crawlers for [various datasets](https://openlobbying.org/datasets) in `datasets/`. At a minimum, each dataset consists of a `config.yml` with metadata and a `crawl.py` script that outputs FollowTheMoney statements in CSV format.

To crawl a dataset, run `uv run muckrake crawl {dataset_name}`. Run `uv run muckrake list` to see available datasets.

Each crawl now creates a `dataset_runs` record in Postgres and stores immutable artifacts under `MUCKRAKE_ARTIFACT_PATH` (defaults to `data/artifacts`). The latest successful run remains mirrored into `data/datasets/{name}/statements.pack.csv` for local compatibility.

### AI-based NER

Many data sources have [composite fields that contain multiple entities](https://openaccess.transparency.org.uk/?meeting=10088). We use LLMs to extract unique entities and relationships from these fields, and store them as candidates in the database for review and approval. See [NER docs](/src/muckrake/extract/ner/README.md) for details.

```bash
# Create extraction candidates for one dataset
uv run muckrake ner-extract open_access --extractor llm --limit 50

# Review candidates in a terminal UI
uv run muckrake ner-review
```

### Dedupe

Our goal is to link entities across datasets to provide a unified view of lobbying and political finance for any given person, company, or organisation.

```bash
# Create dedupe candidates across all datasets
uv run muckrake xref

# Review candidates in a terminal UI
uv run muckrake dedupe
```

We also want to collapse duplicate relationship edges across datasets, especially for ORCL and PRCA. This is done automatically, no review step required.

```bash
uv run muckrake dedupe-edges
```

### Loading

Statements are loaded into Postgres with `uv run muckrake load`. This reads the statements CSV files and applies any approved NER candidates before materialising entities and relationships.

To load from a specific immutable crawl snapshot instead of the local workspace copy:

```bash
uv run muckrake load gb_political_finance --run-id 123
```

For the published site, prefer the release workflow instead of loading directly into the serving database:

```bash
uv run muckrake release-build
uv run muckrake release-publish 1
```


## OpenLobbying

The primary user of Muckrake data is [OpenLobbying](https://openlobbying.org/), an open database of lobbying and political finance data.

Start the API server:

```bash
uv run muckrake server
```

Start the Svelte frontend:

```bash
cd openlobbying
npm run dev
```

In development, frontend requests to `/api/*` are proxied to `http://127.0.0.1:8000` via Vite.

## Environment setup

- Copy `.env.example` to `.env` in the repo root.
- That single repo-root `.env` is used for local Python and frontend development.
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
  - `OPENROUTER_API_KEY`, `LLM_MODEL`, `NER_LLM_PROMPT_FILE`, `LOGFIRE_TOKEN`
- Example:

```bash
cp .env.example .env
```

## Deployment docs

- Deployment runbook: `ops/README.md`
- App deployment assets: `ops/`
- One-command app deploy: `./ops/deploy_to_vps.sh {ip_address}`
