# Changelog

All notable changes to muckrake are recorded here. Versions follow
[semantic versioning](https://semver.org/); while muckrake is below 1.0, a minor
version can change behaviour.

## [0.3.0] - 2026-10-15

Hardening for full-scale ingests: crawls survive bad sources, loads and publishes
are atomic, and publishing to Postgres is about 13 times faster.

### Added

- Crawl units of work: `Dataset.run_unit` runs one source (a file, a page, a
  sheet) and records a failure instead of aborting the crawl. A run with failed
  units ends with the new `partial` status, and `muckrake crawl --retry-failed`
  re-runs only the failed units.
  ([#35](https://github.com/openlobbying/muckrake/pull/35))
- Completeness warnings: `Dataset.warn_incomplete` records that a crawl knowingly
  skipped data and marks the run `partial`; `release-build` reports the warnings
  of every run it includes.
  ([#37](https://github.com/openlobbying/muckrake/pull/37))
- A shared HTTP session for `fetch_*` with retries, backoff and rate limiting.
  ([#22](https://github.com/openlobbying/muckrake/pull/22))
- A Dockerfile and a standalone compose file (Postgres on port 5433, CLI runner
  behind the `tools` profile).
  ([#20](https://github.com/openlobbying/muckrake/pull/20))

### Changed

- `release-publish` on Postgres copies the release pack into a new statement
  table and search view and swaps them in, instead of upserting row by row.
  A full release (5.2M statements) publishes in 8 minutes instead of 107.
  Readers keep seeing the previous release until the swap commits. SQLite keeps
  the row-by-row writer.
  ([#44](https://github.com/openlobbying/muckrake/pull/44))
- `load` and `release-publish` each run in one transaction, so a failure rolls
  back and leaves the previous data intact.
  ([#38](https://github.com/openlobbying/muckrake/pull/38))
- The LevelDB store is imported lazily, so only `xref` needs `plyvel`; the rest
  of the CLI runs without it (for example natively on macOS).
  ([#36](https://github.com/openlobbying/muckrake/pull/36))
- `pydantic-ai-slim` is held below 2, and vulnerable locked dependencies are
  upgraded. ([#42](https://github.com/openlobbying/muckrake/pull/42))
- `org-id` 0.1.1 removes an ID-generation hot loop that dominated crawl time.

### Fixed

- The search-view rebuild no longer hits nomenklatura's statement timeout at
  full scale. ([#40](https://github.com/openlobbying/muckrake/pull/40))
- `parse_day_range` handles ranges across months where the start year is
  omitted, and `_` as a separator.
  ([#23](https://github.com/openlobbying/muckrake/pull/23))

### Development

- ruff, mypy and pre-commit, with all findings fixed
  ([#24](https://github.com/openlobbying/muckrake/pull/24)); test coverage
  across core ([#25](https://github.com/openlobbying/muckrake/pull/25),
  [#33](https://github.com/openlobbying/muckrake/pull/33)); CI on pull requests,
  including a Postgres service
  ([#34](https://github.com/openlobbying/muckrake/pull/34)); a contributing
  guide ([#31](https://github.com/openlobbying/muckrake/pull/31)).

## Earlier versions

See the [GitHub releases](https://github.com/openlobbying/muckrake/releases) for
0.2.1 and before.

[0.3.0]: https://github.com/openlobbying/muckrake/compare/v0.2.1...v0.3.0
