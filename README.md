# muckrake

A reusable pipeline for crawling public data sources into
[FollowTheMoney](https://followthemoney.tech/) (FtM) entities, resolving duplicates
across sources, and publishing immutable releases to a read-only database.
It is partly inspired by [`zavod`](https://zavod.opensanctions.org/) and
[other tools in the FollowTheMoney ecosystem](https://followthemoney.tech/community/stack/).

> [!WARNING]
> This is a work in progress. Expect breaking changes and incomplete features.

muckrake ships no datasets of its own: a project keeps its crawlers in its own
repository and runs muckrake from there. [OpenLobbying](https://github.com/openlobbying/openlobbying)
(UK lobbying and political finance) is the main project built on it.

- [Quickstart](#quickstart)
- [Installation](#installation)
- [How it works](#how-it-works)
- [Guides](#guides): [writing a crawler](#writing-a-crawler), [entity extraction](#entity-extraction-ner), [deduplication](#deduplication), [releases](#releases-and-publishing), [Postgres](#using-postgres)
- Reference: [CLI](docs/cli.md), [environment variables](docs/env.md), [NER](src/muckrake/extract/ner/README.md), [dedupe review](src/muckrake/dedupe/README.md), [changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md)

## Quickstart

Crawl the bundled example dataset, publish it, and search it, using SQLite only
(no Docker, no network access after installation). You need
[uv](https://docs.astral.sh/uv/) and the ICU and LevelDB libraries (see
[Installation](#installation); on macOS, `brew install icu4c pkg-config leveldb`).

```bash
git clone https://github.com/openlobbying/muckrake.git
cd muckrake

# macOS only: let the PyICU build find Homebrew's ICU
export PKG_CONFIG_PATH="$(brew --prefix icu4c)/lib/pkgconfig"
uv sync

# Discover the example dataset in examples/hello_dataset/
export MUCKRAKE_DATASET_PATHS=examples
# release-publish writes to a separate published database, and refuses to run without one
export MUCKRAKE_PUBLISHED_DATABASE_URL=sqlite:///data/published.db

uv run muckrake list
uv run muckrake -v crawl hello       # writes data/datasets/hello/statements.pack.csv
uv run muckrake -v load hello        # loads it into the working DB, data/muckrake.db
uv run muckrake release-build hello  # prints "Built release 1"
uv run muckrake -v release-publish 1 # copies release 1 into data/published.db
uv run muckrake search acme --pretty # finds the two example companies
```

`-v` turns on progress logging; without it, `crawl`, `load` and `release-publish`
print nothing on success. The example crawler is
[`examples/hello_dataset/crawler.py`](examples/hello_dataset/crawler.py): copy it
as the starting point for your own.

## Installation

muckrake needs Python 3.13 (uv installs it) and two system libraries that some
dependencies compile against:

- **ICU** and **pkg-config**, for PyICU (used for name normalisation). Required.
  - macOS: `brew install icu4c pkg-config`. Homebrew doesn't link `icu4c` into
    the default search path, so export
    `PKG_CONFIG_PATH="$(brew --prefix icu4c)/lib/pkgconfig"` before `uv sync`.
  - Debian/Ubuntu: `sudo apt-get install libicu-dev pkg-config`.
- **LevelDB**, for plyvel. Required to install: plyvel is a dependency with no
  binary wheels, so `uv sync` compiles it against the LevelDB headers.
  - macOS: `brew install leveldb`.
  - Debian/Ubuntu: `sudo apt-get install libleveldb-dev`.

  At runtime only the `xref`, `dedupe`, `dedupe-edges` and `export` commands load
  plyvel. On macOS, plyvel builds against Homebrew's LevelDB but fails on import
  (`symbol not found ... leveldb10ComparatorE`), so run those four commands in the
  container (see [Using Postgres](#using-postgres)); every other command runs
  natively. Making plyvel an optional dependency is tracked in
  [Make plyvel (LevelDB) an optional extra](https://github.com/openlobbying/muckrake/issues/54).

Then, in a clone of this repo, `uv sync`. To use muckrake from another project,
add it as a dependency (`uv add muckrake`) and run `uv run muckrake` from that
project's root.

Configuration is through environment variables, read after loading the nearest
`.env` file from the current directory upward; `.env.example` is a commented
template, and [docs/env.md](docs/env.md) lists every variable.

## How it works

A project has a `datasets/` directory with one subdirectory per data source, each
holding a `config.yml` and a `crawler.py`. muckrake discovers datasets in
`./datasets/` under the current directory and in any `MUCKRAKE_DATASET_PATHS`.
Data moves through these stages:

1. **Crawl** (`muckrake crawl <name>`) runs the dataset's `crawl(dataset)`
   function, which emits FtM entities as statements. Each crawl records a row in
   `dataset_runs` and writes an immutable artifact under `MUCKRAKE_ARTIFACT_PATH`
   (default `data/artifacts/`); the latest successful or `partial` run is mirrored to
   `data/datasets/<name>/statements.pack.csv`.
2. **Extract** (`ner-extract`, `ner-review`, optional) splits text fields that
   name several entities at once into separate entity candidates for review.
3. **Load** (`muckrake load`) reads the statement packs, applies approved
   extraction candidates, and writes the statements into the working database.
4. **Deduplicate** (`xref`, `dedupe`, `dedupe-edges`) suggests, reviews and
   records which entities are the same, using
   [nomenklatura](https://github.com/opensanctions/nomenklatura)'s resolver.
5. **Release** (`release-build`, `release-publish`) snapshots the latest dataset
   runs into an immutable release, and publishes it into the separate
   **published database** that applications read.

There are two databases:

- The **working database** (`MUCKRAKE_DATABASE_URL`, default SQLite at
  `data/muckrake.db`) holds everything the pipeline produces and decides: crawl
  runs, loaded statements, the resolver, extraction candidates, releases, and the
  HTTP cache that `dataset.fetch_text/json/html` use (the `cache` table).
- The **published database** (`MUCKRAKE_PUBLISHED_DATABASE_URL`) holds only the
  current release's statements and resolver, for applications to read.
  `release-publish` refuses to run unless it is a different database from the
  working one. Never `load` directly into it.

The `add`, `get`, `search` and `update` commands read and edit single entities in
the working database, for building a graph by hand during an investigation.

Anything that uses FtM must `import muckrake` first: on import it merges any
schema extensions (from `./ftm_schema_ext/` or `MUCKRAKE_FTM_SCHEMA_PATHS`) into
the FtM model and points `FTM_MODEL_PATH` at the result.

## Guides

### Writing a crawler

At minimum a dataset is a `config.yml` (FtM dataset metadata; `name` is what you
pass to `muckrake crawl`) and a `crawler.py` defining `crawl(dataset)`. The
crawler creates entities with `dataset.make(schema)`, gives each a stable ID with
`dataset.make_id(...)` (pass `reg_nr=` and `register=` to use an
[org-id](https://org-id.guide/) identifier such as `GB-COH-01234567`), and writes
them with `dataset.emit(entity)`. See the
[FtM schema explorer](https://followthemoney.tech/explorer/schemata/) for schemata
and properties.

Fetch sources with `dataset.fetch_text`, `fetch_json` or `fetch_html` (cached in
the working database's `cache` table for `cache_days=N`) or `dataset.fetch_resource`
(downloaded to `data/datasets/<name>/resources/`). Requests share a session that
retries with backoff; set `MUCKRAKE_HTTP_MIN_INTERVAL` to rate-limit each host.

A crawler should crash on data it can't interpret rather than emit a guess.

#### Units of work and `--retry-failed`

A crawler can split its work into independently retryable units (one source file,
one page, one record) by wrapping each in `dataset.run_unit(key, func, *args)`. A
unit's statements reach the pack only if `func` returns. If it raises, the unit is
recorded as failed, nothing from it is emitted, and the crawl carries on. A crawl
that completes with failed units finishes as `partial`: its output is usable by
`load` and `release-build`, and the failures are counted by error type in the run's
stats and the end-of-crawl log. Errors outside a unit still fail the whole crawl.

Each run writes a `units.jsonl` ledger next to its pack, recording where every
succeeded unit sits in the pack. `uv run muckrake crawl <name> --retry-failed`
copies the units that succeeded in the dataset's latest crawl into a new run and
re-runs everything else. That covers both retrying failures (e.g. after a parser
fix) and resuming a crawl that crashed or was killed partway. Pack and ledger are
written in place under the run's artifact directory as the crawl goes, so even a
killed crawl leaves its completed units behind.

#### Completeness warnings

When a crawler knows its output is missing something (a pagination cap was hit,
an API returned fewer items than it reported, a linked file has gone), it records
it with `dataset.warn_incomplete(reason, **context)` rather than only logging it.
Keep `reason` a fixed phrase and put the specifics in `context`. The run finishes
as `partial`, the warnings are counted by reason in the end-of-crawl log and
listed in the run's stats, and warnings raised inside a unit are carried over by
`--retry-failed`. `release-build` logs every `partial` input and records what it's
missing (failed units and warnings by reason) in the release manifest.

### Entity extraction (NER)

Source data often packs several entities into one field, such as a list of
meeting attendees in one cell. `ner-extract` sends such texts to a splitter (a
deterministic `delimiter` splitter, or an LLM via OpenRouter or Anthropic) and
stores the result as candidates in the working database; `ner-review` approves or
rejects them, and only approved candidates are applied by `load`, `xref` and
`release-build`. `ner-export` and `ner-import` keep candidates outside the
database, so paid LLM results survive a lost database.

```bash
uv run muckrake ner-extract <dataset> --extractor llm --limit 50
uv run muckrake ner-review
```

`--extractor llm` needs `LLM_MODEL` with a provider prefix
(`openrouter:<model>` or `anthropic:<model>`) and the matching API key. See the
[NER docs](src/muckrake/extract/ner/README.md).

### Deduplication

```bash
uv run muckrake xref          # suggest pairs of entities that may be the same
uv run muckrake dedupe        # review the suggestions in a terminal UI
uv run muckrake dedupe-edges  # merge duplicate Representation edges, no review step
```

Decisions are stored in the resolver table in the working database and applied
when a release is published. `xref` considers at most 50,000 candidate pairs per
run (`--limit`). Set `MUCKRAKE_PROFILE_URL` to show a link to each entity in your
own application in the review UI. These commands, and `export`, need LevelDB (see
[Installation](#installation)). muckrake also provides the backend for a
multi-user web review UI, which an application can build on; see the
[dedupe docs](src/muckrake/dedupe/README.md).

### Releases and publishing

```bash
uv run muckrake release-build                      # every discovered dataset
uv run muckrake release-build <dataset> <dataset>  # or just these
uv run muckrake release-list
uv run muckrake release-publish <release-id>
```

`release-build` takes the latest successful (or `partial`) run of each dataset
and fails if any dataset has none, so name the datasets you want when some have
never been crawled. Set `MUCKRAKE_PUBLISHED_DATABASE_URL` to a separate database
before publishing.

`load` is atomic: every dataset in it is cleared and reloaded in a single
transaction, so a load that fails partway leaves the previously loaded statements
in place. A dataset with no statements pack is skipped with a warning, and its
loaded statements are kept. `load <dataset> --run-id N` loads a specific
immutable crawl run instead of the latest.

Publishing writes the release's statements in a single transaction, so readers
keep seeing the previous release until it commits, and a failure leaves the
previous statements in place. On Postgres, the release is loaded with `COPY` into
a new statement table, indexed and given its own search view, then swapped in with
renames, so readers only wait for the swap; a release of ~5M statements publishes
in minutes. On SQLite, the published statements are cleared and rewritten row by
row. One caveat: the resolver (deduplication decisions) is copied from the working
database first, in its own transaction, so a publish that fails after that step
leaves the previous statements with the current resolver.

### Using Postgres

SQLite is the default and needs no setup. For larger datasets, run Postgres with
the bundled compose file (Postgres 18 on host port **5433**; an init script
creates the `muckrake` and `muckrake_published` databases):

```bash
docker compose up -d db
```

and set, in `.env`:

```bash
MUCKRAKE_DATABASE_URL=postgresql://muckrake:muckrake@localhost:5433/muckrake
MUCKRAKE_PUBLISHED_DATABASE_URL=postgresql://muckrake:muckrake@localhost:5433/muckrake_published
```

The compose file also has a CLI runner with LevelDB built in:
`docker compose run --rm muckrake <command>` is the container equivalent of
`uv run muckrake <command>`. It bind-mounts this repository at `/work` (its
working directory, so `datasets/`, `data/` and `.env` come from the host) and uses
the compose Postgres databases, so run the whole pipeline through it rather than
mixing it with a native SQLite setup.
