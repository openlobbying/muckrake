# Changelog

All notable changes to muckrake are recorded here. Versions follow
[semantic versioning](https://semver.org/); while muckrake is below 1.0, a minor
version can change behaviour.

## [Unreleased]

### Changed

- The `ner-review` screen is rebuilt. Entities are in a table you move through
  with the arrow keys, with references shown as the entity they point to. Every
  edit happens on the screen, with no external editor: `Enter` edits an entity in
  a form, `a` adds one, `d` deletes one and the references to it, `s` splits one
  into a Person, a body and an Employment (`Ctrl+T` moves the text after the
  cursor into the body's name), and `e` edits the JSON with checks as you type. `z` undoes the last decision, and a progress line shows your place
  and, for a sample, its running counts, split by reviewer once more than one
  has decided. The prompt review used without a
  terminal still opens `$EDITOR` for `e`.
- `ner-review` records who is reviewing: `--reviewer NAME`, or `MUCKRAKE_REVIEWER`, or the
  login name (`root` is refused). It no longer records every person as `muckrake/ner-review`.
  Reviewer names give the kind of decision: `muckrake/auto` is automatic, `model:<name>` is a
  model, and any other name is a person. `review_kind()` reads them, and `sample_results()`
  adds a `by_kind` breakdown. `review_candidate()` now needs a `reviewer`.

### Added

- `ner-review --sample N` reviews a sample of N random candidates that `--auto`
  approved, so the precision of its splits can be measured. N is the sample's
  size: only enough candidates to reach it are drawn, so running the same
  command again resumes the review. With `--rejected` it samples the candidates `--auto` rejected
  instead, to measure how often a composite name was left whole. After the
  review it prints the pool's counts; `sample_results` returns them for both
  pools, with approvals split into unedited and edited, so a corrected split
  isn't counted as right. `ner_candidates` gains nullable `sampled_at` and
  `sampled_status` columns.
- The review UI records when a reviewer saves an edited extraction, in a new
  nullable `ner_candidates.edited_at` column, and keeps the extraction from
  before the first edit in `original_extraction_json`.
- `sample_results` also breaks each pool's counts down by reviewer, under
  `by_reviewer`, so decisions by a person and by a model are reported apart; the
  pool's own counts stay the totals. The command prints a line per reviewer.
- `sample_results` also counts per entity (checked, kept, removed, added),
  comparing an edited extraction with its original, so the accuracy of the
  extracted entities can be measured as well as that of whole splits.
  Candidates edited before originals were kept count per split only, as
  `edited_without_original`.
- `init_database` adds the four new columns to existing tables, and
  `ner-export` / `ner-import` carry them (older exports import with them unset).

### Fixed

- `xref` removes open suggestions whose source or target is no longer in the store before
  it writes new ones, and logs how many. They pointed at entities that had gone, such as
  composites replaced by NER splits, inflated the review queue, and would have become
  judgements about nothing under an auto-merge threshold. Judgements are never removed
  ([xref keeps suggestions for entities that no longer exist](https://github.com/openlobbying/muckrake/issues/55)).
- Applying an approved NER split no longer merges relationships from different
  splits. A fragment without a name, such as an `Employment`, was given an ID
  hashed from its properties before its `$ref:` values were resolved, so every
  split's "`$ref:p1` employed by `$ref:o1`" with the same role shared one ID.
  The ID is now hashed after the refs are resolved. Nameless fragments get new
  IDs at the next `load`
  ([NER: relationship fragments from different splits share an ID, merging unrelated relationships](https://github.com/openlobbying/muckrake/issues/73)).

## [0.5.1] - 2026-11-25

A patch release: a release over 2 GiB can be built.

### Fixed

- `release-build` no longer fails on a release pack over 2 GiB: `size_bytes` in
  `dataset_run_artifacts` and `release_artifacts` is now `BIGINT`. On Postgres,
  `init_database` widens the column in existing tables (SQLite's integers are
  already 64-bit).

## [0.5.0] - 2026-11-25

`crawl` needs far less memory for large datasets. A minor version:
`load_timestamps` returns a `FirstSeen` instead of a `dict`.

### Changed

- `crawl` holds the previous run's `first_seen` timestamps in far less memory:
  `muckrake.timestamps.FirstSeen` keeps each SHA-1 statement ID as a 20-byte
  digest in a sorted numpy array and each timestamp as an index into the
  distinct ones, ~24 bytes a statement instead of ~190 in a `dict`. Loading a
  10.7M-statement pack now peaks at 731 MB and holds 250 MB, down from 2.2 GB
  and 2.05 GB; the output is unchanged. `load_timestamps` returns a `FirstSeen`,
  and `Dataset(timestamps=...)` takes one (a mapping still works). numpy is now
  a direct dependency (it already came with pandas).

## [0.4.0] - 2026-11-25

muckrake now runs on the current nomenklatura and followthemoney, and the
published database is faster to read. A minor version: `get_resolver()` is
gone and the minimum dependency versions went up.

### Added

- `release-publish` gives the published database a partial index on
  `statement(value)` for identifiers (`ix_statement_value_identifier`, SQLite
  and Postgres), which serves lookups by registration or tax number
  (`prop_type = 'identifier' AND value = ...`). They used to scan every
  statement.

### Changed

- Ported to nomenklatura 4.18 and followthemoney 4.11, now the minimum versions
  (`nomenklatura>=4.18`, `followthemoney>=4.11`), so consumers no longer need to
  pin `nomenklatura<4.6`. nomenklatura's `Resolver` and `Cache` now run on a
  `nomenklatura.db.Session` and `SQLStore` takes an engine; muckrake follows.
- `muckrake.db.get_resolver()` is replaced by `open_resolver()`, a context
  manager that yields a loaded resolver and commits its writes when the block
  exits (rolling back if it raises), and `get_linker()` for read-only access to
  the merges.
- `xref` commits its suggestions in batches as it runs (nomenklatura's own
  checkpoints), so an interrupted run keeps what it suggested so far. It used to
  run in one transaction.
- Suggestions that a judgement supersedes are now soft-deleted and stay in the
  `resolver` table until `xref-prune`; nomenklatura used to hard-delete them on
  every commit.
- The statement table gets nomenklatura's partial index on `value` for
  entity-typed statements (`ix_statement_value_entity`), which serves "what
  points at this entity?" queries. It is created in new databases, in each
  Postgres release publish, and in an existing database the first time a SQL
  store opens it (a one-off index build on a large database).
- Postgres search (`search_entities`, the `search` command, applications' search
  endpoints) is about ten times faster on large releases: its fuzzy-match
  conditions use pg_trgm's `%` and `<%` operators, which the `entity_search`
  trigram indexes serve, instead of comparing `similarity()` to a threshold,
  which scanned every row. Results are the same, except that a similarity
  exactly equal to a threshold (0.25, or 0.55 for word similarity) now matches.

### Fixed

- `muckrake add` still rejects an entity missing a required property:
  followthemoney 4.11's `Schema.validate` only checks the properties it is
  given, so muckrake now passes the required ones too.

## [0.3.1] - 2026-10-15

Follow-up to 0.3.0 from the documentation audit: dependency and loading fixes,
the last consumer-specific values removed from the dedupe code, and checks that
keep the docs accurate.

### Changed

- `org-id>=0.1.1` is now required, so installs always get the version without
  the ID-generation hot loop (0.3.0 allowed 0.1.0).
- The `dedupe` TUI no longer links entities to a hard-coded website. Set
  `MUCKRAKE_PROFILE_URL` (e.g. `https://example.org/entity/%s`) to show links.
- Judgements recorded through the web-review backend
  (`record_dedupe_judgement`, `record_dedupe_cluster_judgement`) no longer get a
  built-in application prefix on the resolver user. Callers that want one pass
  `user_prefix=`.

### Fixed

- OpenRouter models failed to load with the locked `openai` 2.21.0, which is older than
  the locked `pydantic-ai-slim` needs; `openai` is now locked at 3.31.0, and a test loads
  each LLM provider. ([OpenRouter models fail to load with the locked openai 2.21.0](https://github.com/openlobbying/muckrake/issues/56))
- Every command creates the directory of a SQLite database before opening it,
  so a fresh checkout without `data/` no longer fails with "unable to open
  database file".
- Enabling Logfire for LLM extraction no longer loads a second `.env` from the
  muckrake package's parent directory, which ignored `MUCKRAKE_ENV_FILE` and
  `ENVIRONMENT=production`.

### Documentation

- Correction to 0.3.0: LevelDB (`plyvel`) is needed by `xref`, `dedupe`,
  `dedupe-edges` and `export`, not only `xref`; every other command runs without it.
- `release-publish` requires `MUCKRAKE_PUBLISHED_DATABASE_URL` to name a separate
  database; the docs had called it optional.
- Correction to 0.3.0: a failed `release-publish` leaves the previous statements
  in place, but not the previous resolver, which is copied first in its own
  transaction.
- A README quickstart with a bundled example dataset (`examples/hello_dataset/`),
  a self-contained contributing guide, and generated references for the CLI
  (`docs/cli.md`) and environment variables (`docs/env.md`).

### Development

- CI checks that the generated references are current, that muckrake mentions no
  consuming project (`scripts/litmus.sh`), and that Markdown links resolve. The
  `Publish` workflow installs ICU like CI does.
- Moved the unmaintained crawler stubs in `datasets_to_do/` to the openlobbying repo (`datasets_parked/`).

## [0.3.0] - 2026-10-15

Hardening for full-scale ingests: crawls survive bad sources, loads and publishes
are atomic, publishing to Postgres is about 13 times faster, and LLM entity
extraction runs at full scale with its paid results kept.

### Added

- Crawl units of work: `Dataset.run_unit` runs one source (a file, a page, a
  sheet) and records a failure instead of aborting the crawl. A run with failed
  units ends with the new `partial` status, and `muckrake crawl --retry-failed`
  re-runs only the failed units.
  ([Crawl units of work: skip-and-report failures, partial runs, --retry-failed](https://github.com/openlobbying/muckrake/pull/35))
- Completeness warnings: `Dataset.warn_incomplete` records that a crawl knowingly
  skipped data and marks the run `partial`; `release-build` reports the warnings
  of every run it includes.
  ([Completeness warnings: Dataset.warn_incomplete marks runs partial](https://github.com/openlobbying/muckrake/pull/37))
- Entity extraction at full scale ([NER at full scale: concurrent extraction, auto review, export/import, Anthropic](https://github.com/openlobbying/muckrake/pull/47)):
  - `ner-extract --workers N` extracts N texts concurrently, and each distinct
    text is extracted once across all datasets (approved candidates already
    applied by text everywhere).
  - `ner-review --auto` approves every pending split and rejects extractions
    that only repeat the source text, recorded as reviewer `muckrake/auto`.
    Decisions made in the review TUI are never overwritten.
  - `ner-export` / `ner-import` save and restore candidates and review
    decisions as JSON lines, so paid extractions survive a lost database and
    are never repeated. Import never overwrites a local decision.
  - The LLM extractor can use Anthropic models (`LLM_MODEL=anthropic:<model>`
    with `ANTHROPIC_API_KEY`) as well as OpenRouter.
- A shared HTTP session for `fetch_*` with retries, backoff and rate limiting.
  ([Resilient fetch layer: shared polite session with retry, backoff and rate limiting](https://github.com/openlobbying/muckrake/pull/22))
- A Dockerfile and a standalone compose file (Postgres on port 5433, CLI runner
  behind the `tools` profile).
  ([Containerise: Dockerfile + standalone compose](https://github.com/openlobbying/muckrake/pull/20))

### Changed

- `release-publish` on Postgres copies the release pack into a new statement
  table and search view and swaps them in, instead of upserting row by row.
  A full release (5.2M statements) publishes in 8 minutes instead of 107.
  Readers keep seeing the previous release until the swap commits. SQLite keeps
  the row-by-row writer.
  ([Publish to Postgres with COPY and a table swap](https://github.com/openlobbying/muckrake/pull/44))
- `load` and `release-publish` each run in one transaction, so a failure rolls
  back and leaves the previous data intact.
  ([Atomic load and publish: one transaction, rolled back on failure](https://github.com/openlobbying/muckrake/pull/38))
- The LevelDB store is imported lazily, so only `xref` needs `plyvel`; the rest
  of the CLI runs without it (for example natively on macOS).
  ([Import the LevelDB store lazily so only xref needs plyvel](https://github.com/openlobbying/muckrake/pull/36))
- `pydantic-ai-slim` is held below 2, and vulnerable locked dependencies are
  upgraded. ([Upgrade vulnerable locked dependencies; hold pydantic-ai below 2](https://github.com/openlobbying/muckrake/pull/42))
- `ner-extract` only sends texts containing `,`, `;` or `:`. "and", "&" and
  brackets alone are nearly always one name, and sending them wasted about a
  quarter of LLM calls. ([NER at full scale: concurrent extraction, auto review, export/import, Anthropic](https://github.com/openlobbying/muckrake/pull/47))
- `org-id` 0.1.1 removes an ID-generation hot loop that dominated crawl time.

### Fixed

- The search-view rebuild no longer hits nomenklatura's statement timeout at
  full scale. ([Lift nomenklatura's statement timeout for the search-view rebuild](https://github.com/openlobbying/muckrake/pull/40))
- `parse_day_range` handles ranges across months where the start year is
  omitted, and `_` as a separator.
  ([parse_day_range: cross-month ranges with omitted start year and underscore separator](https://github.com/openlobbying/muckrake/pull/23))

### Development

- ruff, mypy and pre-commit, with all findings fixed
  ([Adopt tooling baseline: ruff, mypy, pre-commit](https://github.com/openlobbying/muckrake/pull/24)).
- Test coverage across core
  ([Introduce test coverage across muckrake core](https://github.com/openlobbying/muckrake/pull/25),
  [Tests: strict xfail for desired load/release behaviour; fix stale org-id pin](https://github.com/openlobbying/muckrake/pull/33)).
- CI on pull requests
  ([Add CI on PRs; relock dev dependencies](https://github.com/openlobbying/muckrake/pull/34)),
  with a Postgres service for the Postgres-only tests
  ([Publish to Postgres with COPY and a table swap](https://github.com/openlobbying/muckrake/pull/44)).
- A contributing guide
  ([Add CONTRIBUTING.md](https://github.com/openlobbying/muckrake/pull/31)).

## Earlier versions

See the [GitHub releases](https://github.com/openlobbying/muckrake/releases) for
0.2.1 and before.

[Unreleased]: https://github.com/openlobbying/muckrake/compare/v0.5.1...develop
[0.5.1]: https://github.com/openlobbying/muckrake/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/openlobbying/muckrake/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/openlobbying/muckrake/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/openlobbying/muckrake/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/openlobbying/muckrake/compare/v0.2.1...v0.3.0
