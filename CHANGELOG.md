# Changelog

All notable changes to muckrake are recorded here. Versions follow
[semantic versioning](https://semver.org/); while muckrake is below 1.0, a minor
version can change behaviour.

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

[Unreleased]: https://github.com/openlobbying/muckrake/compare/v0.3.0...develop
[0.3.1]: https://github.com/openlobbying/muckrake/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/openlobbying/muckrake/compare/v0.2.1...v0.3.0
