A reusable framework for creating and storing [FollowTheMoney](https://followthemoney.tech/) entities.

> [!WARNING]
> This is a work in progress. Expect breaking changes and incomplete features.

## Muckrake

Muckrake is the data pipeline. It is partially inspired by [`zavod`](https://zavod.opensanctions.org/) and [other tools in the FollowTheMoney ecosystems](https://followthemoney.tech/community/stack/).

Run `uv run muckrake --help` for a full list of available commands.

Install Python dependencies with `uv sync`. This now includes the external `org-id` package used for structured organization identifiers.

Muckrake also extends the FollowTheMoney model with local `Meeting`, `Donation`, `Gift`, and `Hospitality` schemata. The package bootstrap configures `FTM_MODEL_PATH` automatically so crawls, loads, exports, releases, and the API all use the same model inside this repo.

OpenLobbying-specific code now lives in the sibling `../openlobbying/` repository. That repo owns:

- the OpenLobbying dataset crawlers
- the OpenLobbying FastAPI application
- the OpenLobbying Svelte frontend
- deployment assets for the public site

### Crawlers

Muckrake discovers crawler configs from `./datasets/` in the current working directory, any paths listed in `MUCKRAKE_DATASET_PATHS`, and the sibling `../openlobbying/datasets/` tree used in this workspace. At a minimum, each dataset consists of a `config.yml` with metadata and a `crawler.py` script that outputs FollowTheMoney statements in CSV format.

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

The primary user of Muckrake data is [OpenLobbying](https://openlobbying.org/), an open database of lobbying and political finance data. See `../openlobbying/README.md` for app setup, API serving, and frontend development.

## Environment setup

- Copy `.env.example` to `.env` in the repo root.
- By default `muckrake` loads the nearest `.env` from the current working directory upward. Override that with `MUCKRAKE_ENV_FILE` if needed.
- Required for local development:
  - `MUCKRAKE_DATABASE_URL`
- Common local settings:
  - `MUCKRAKE_PUBLISHED_DATABASE_URL` for a separate published API database
- Optional local overrides:
  - `MUCKRAKE_DATA_PATH`
  - `MUCKRAKE_ARTIFACT_PATH`
  - `MUCKRAKE_DATASET_PATHS`
  - `MUCKRAKE_ENV_FILE`
  - `FTM_MODEL_PATH` if you need to override the repo's merged local FollowTheMoney model
  - `OPENROUTER_API_KEY`, `LLM_MODEL`, `NER_LLM_PROMPT_FILE`, `LOGFIRE_TOKEN`
- Example:

```bash
cp .env.example .env
```

## Consumers

- `../openlobbying/`: OpenLobbying application repo built on top of `muckrake`
- `../us-congress-lobbying/`: project-specific investigative sandbox
