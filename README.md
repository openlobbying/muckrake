A reusable framework for creating and storing [FollowTheMoney](https://followthemoney.tech/) entities.

> [!WARNING]
> This is a work in progress. Expect breaking changes and incomplete features.

## Muckrake

Muckrake is the data pipeline. It is partially inspired by [`zavod`](https://zavod.opensanctions.org/) and [other tools in the FollowTheMoney ecosystems](https://followthemoney.tech/community/stack/).

Run `uv run muckrake --help` for a full list of available commands.

Install Python dependencies with `uv sync`. This now includes the external `org-id` package used for structured organization identifiers.

OpenLobbying-specific code now lives in the sibling `../openlobbying/` repository. That repo owns:

- the OpenLobbying dataset crawlers
- the OpenLobbying FastAPI application
- the OpenLobbying Svelte frontend
- any project-specific FtM schema extensions
- deployment assets for the public site

### Crawlers

Muckrake discovers crawler configs from `./datasets/` in the current working directory and any paths listed in `MUCKRAKE_DATASET_PATHS`. At a minimum, each dataset consists of a `config.yml` with metadata and a `crawler.py` script that outputs FollowTheMoney statements in CSV format.

To crawl a dataset, run `uv run muckrake crawl {dataset_name}`. Run `uv run muckrake list` to see available datasets.

Each crawl now creates a `dataset_runs` record in Postgres and stores immutable artifacts under `MUCKRAKE_ARTIFACT_PATH` (defaults to `data/artifacts`). The latest successful run remains mirrored into `data/datasets/{name}/statements.pack.csv` for local compatibility.

#### Units of work and `--retry-failed`

A crawler can split its work into independently retryable units (one source file, one page, one record) by wrapping each in `dataset.run_unit(key, func, *args)`. A unit's statements reach the pack only if `func` returns. If it raises, the unit is recorded as failed, nothing from it is emitted, and the crawl carries on. A crawl that completes with failed units finishes as `partial`: its output is usable by `load` and `release-build`, and the failures are counted by error type in the run's stats and the end-of-crawl log. Errors outside a unit still fail the whole crawl.

Each run writes a `units.jsonl` ledger next to its pack, recording where every succeeded unit sits in the pack. `uv run muckrake crawl {dataset_name} --retry-failed` copies the units that succeeded in the dataset's latest crawl into a new run and re-runs everything else. That covers both retrying failures (e.g. after a parser fix) and resuming a crawl that crashed or was killed partway. Pack and ledger are written in place under the run's artifact directory as the crawl goes, so even a killed crawl leaves its completed units behind.

#### Completeness warnings

When a crawler knows its output is missing something (a pagination cap was hit, an API returned fewer items than it reported, a linked file has gone), it records it with `dataset.warn_incomplete(reason, **context)` rather than only logging it. Keep `reason` a fixed phrase and put the specifics in `context`. The run finishes as `partial`, the warnings are counted by reason in the end-of-crawl log and listed in the run's stats, and warnings raised inside a unit are carried over by `--retry-failed`. `release-build` logs every `partial` input and records what it's missing (failed units and warnings by reason) in the release manifest.

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

The primary user of Muckrake data is [OpenLobbying](https://openlobbying.org/), an open database of lobbying and political finance data. See `../openlobbying/README.md` for app setup, API serving, and frontend development.

## Environment setup

- Copy `.env.example` to `.env` in the repo root.
- By default `muckrake` loads the nearest `.env` from the current working directory upward. Override that with `MUCKRAKE_ENV_FILE` if needed.
- Default local database setup:
  - working DB: `sqlite:///data/muckrake.db`
  - published DB: same as the working DB unless `MUCKRAKE_PUBLISHED_DATABASE_URL` is set
- Required only if you want Postgres:
  - `MUCKRAKE_DATABASE_URL`
- Common local settings:
  - `MUCKRAKE_PUBLISHED_DATABASE_URL` for a separate published API database
- Optional local overrides:
  - `MUCKRAKE_DATA_PATH`
  - `MUCKRAKE_ARTIFACT_PATH`
  - `MUCKRAKE_DATASET_PATHS`
  - `MUCKRAKE_FTM_SCHEMA_PATHS`
  - `MUCKRAKE_ENV_FILE`
  - `FTM_MODEL_PATH` if you need to override the merged FollowTheMoney model entirely
  - `OPENROUTER_API_KEY`, `LLM_MODEL`, `NER_LLM_PROMPT_FILE`, `LOGFIRE_TOKEN`
- Example:

```bash
cp .env.example .env
```

## Consumers

- `../openlobbying/`: OpenLobbying application repo built on top of `muckrake`
- `../us-congress-lobbying/`: project-specific investigative sandbox
