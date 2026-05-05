This dataset crawls UK government transparency releases from GOV.UK: meetings, gifts, hospitality, travel, and some outside-employment data.

Your job is usually to add schema JSON files in `schemas/` for unresolved sheet fingerprints.

## Preferred Loop

Use `uv` for all commands.

1. Run `uv run python -m datasets.gb.gov_transparency.tools.next_blocker`.
2. If it returns:
   - `unknown_fingerprint`: create the matching schema in `schemas/<fingerprint>.json`
   - `schema_validation_failed`, `extraction_failed`, or `entity_emission_failed`: fix the reported schema/code blocker first
   - `NO_BLOCKER`: run `uv run python -m datasets.gb.gov_transparency.tools.next_unknown` to continue with pure unknowns if needed
3. Validate the affected cached file.
4. Repeat.

Use `uv run muckrake crawl gb_gov_transparency` only as an occasional integration check, not as the default loop.

## Commands

Run tests:

```bash
uv run pytest tests/test_gov_transparency_fingerprint.py tests/test_gov_transparency_schema.py tests/test_gov_transparency_extract.py tests/test_gov_transparency_normalise.py tests/test_gov_transparency_crawler.py
```

Crawl-path blocker finder:

```bash
uv run python -m datasets.gb.gov_transparency.tools.next_blocker
```

Unknown-fingerprint finder in crawl order:

```bash
uv run python -m datasets.gb.gov_transparency.tools.next_unknown
```

Partial crawl output for UI/database inspection:

```bash
uv run muckrake crawl gb_gov_transparency --output - > partial-gov.pack.csv
```

## Schema Rules

Top-level fields:

- `fingerprint`: must match the filename
- `sheet_type`: `data`, `notes`, or `ignore`
- `reason`: required for `notes` and `ignore`
- `activity_type`: required for `data`; one of `meetings`, `gifts`, `hospitality`, `travel`, `outside_employment`
- `subject`, `layout`, `date`, `mapping`, `role_mode`

Canonical mapping fields:

- `official_name`
- `counterparty_name`
- `summary`
- `amount`
- `outcome_text`
- `location`

Date modes:

- `none`
- `provenance_period`
- `column`
- `column_range`

Common parser types:

- `strptime`
- `excel_serial`
- `iso_datetime`
- `day_range`
- `month_name`
- `month_name_from_period`

## Classification

- Use `data` for real activity tables, even if the sampled file is nil-only.
- Use `notes` for explanatory tabs like `Notes`.
- Use `ignore` for helper sheets, empty sheets, collapsed single-column garbage, or layouts that do not fit the crawler model.

## Practical Tips

- If a crawl-path blocker exists, prefer `tools.next_blocker` over `tools.next_unknown`.
- If entity emission fails with `Cannot emit activity without official_name`, the sheet often needs `layout.fill_down_columns: [0]`.
- If fill-down still does not work, check whether `layout.data_start_offset` skips the seed row. Sometimes the seed row must be included so later rows inherit the official name.
- Prefer fixing header detection when the same detector miss repeats across multiple files. Use schema-level `data_start_offset` only when the issue is local to one layout.
- Do not use `strptime` without a year for short values like `10-Oct` or `08-May`; Python will default them to 1900. Prefer `iso_datetime` so the publication period year is used.
- Some files mix formats in one column: `dd/mm/YYYY`, `m/d/YYYY`, `YYYY-MM-DD HH:MM:SS`, month names, and day ranges. Inspect several real rows before choosing parser order.
- Nil-only data sheets often need extra `layout.nil_return_markers` such as `-`.
- Common recurring footer rows should be handled with `layout.skip_row_prefixes`, not special-case code.
- Senior-official travel expense ledgers with `AIR`, `RAIL`, `HOTEL`, or `TAXI` rows are usually `ignore`, not `travel`.
- Chequers/guest-list layouts often need `subject.source: "provenance"` and sometimes `role_mode: "hosted_by_official"`.

## Constraints

- Crash loudly on ambiguity. Do not guess.
- Prefer minimal schemas and minimal code changes.
- Do not edit unrelated datasets.
- Do not commit, push, or open PRs unless explicitly asked.
