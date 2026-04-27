## Purpose

This dataset crawls UK government transparency publications from GOV.UK and processes them in these stages:

1. Discovery via the GOV.UK Content API
2. Normalisation into `NormalisedSheet`
3. Fingerprinting of each sheet layout
4. Schema lookup and validation
5. Row extraction
6. Entity emission

If you are working on this dataset as an agent, your most common task is to create a new schema file for an unknown fingerprint.

## Files

Key files in this dataset:

- `crawler.py`: orchestrates discovery, normalisation, fingerprinting, schema lookup, extraction, emission
- `normalise.py`: file bytes to `list[NormalisedSheet]`
- `fingerprint.py`: detects a stable header row and computes a structural fingerprint
- `schema.py`: loads and validates schema JSON files from `schemas/`
- `extract.py`: applies a schema to a sheet and produces canonical row dicts
- `entities.py`: emits FTM entities from extracted rows
- `types.py`: shared dataclasses like `Provenance`
- `schemas/*.json`: one schema per known fingerprint

## Your Job

When the crawler reports `UNKNOWN FINGERPRINT: <fingerprint>`, your job is usually:

1. Inspect the logged sheet preview and provenance.
2. Find the matching cached source file in `data/datasets/gb_gov_transparency/resources/`.
3. Confirm the actual header row and data rows.
4. Decide whether the sheet is:
   - `data`
   - `notes`
   - `ignore`
5. If it is `data`, create `schemas/<fingerprint>.json`.
6. Validate the schema against the cached file.
7. Prefer the smallest correct schema.

## Schema Format

Each schema JSON maps to the `Schema` dataclass in `schema.py`.

Important fields:

- `fingerprint`: must match the filename and actual computed fingerprint
- `sheet_type`: `data`, `notes`, or `ignore`
- `activity_type`: one of:
  - `meetings`
  - `gifts`
  - `hospitality`
  - `travel`
  - `outside_employment`
  - `other`
- `data_start_offset`: usually `1`
- `fill_down_columns`: columns where blanks mean “same as row above”
- `nil_return_markers`: markers that mean the row is not a real activity
- `date_source`:
  - `column`
  - `none`
- `date_column`: required if `date_source == "column"`
- `date_format`: only for day-level column dates when a fixed `strptime` format is valid
- `date_precision`:
  - `day`
  - `day_or_month`
  - `month`
  - `quarter`
- `columns`: mapping from canonical field names to source column indexes

Canonical fields currently supported:

- required for `data`: `minister_name`
- optional: `counterpart_raw`, `purpose`, `gift_description`, `gift_value`, `outcome`, `destination`, `cost`

## How To Decide Schema Fields

### `sheet_type`

Use:

- `notes` for explanatory tabs like `Notes`
- `ignore` for helper sheets like `Sheet2`
- `data` only for real activity rows

### `data_start_offset`

Usually `1` because data starts right after the detected header row.

If the header row is followed by a spacer row or a repeated title row, increase it only if necessary.

### `fill_down_columns`

Use this when a workbook lists a minister/adviser once and leaves following rows blank.

Common examples:

- ODS ministerial sheets from older Cabinet Office workbooks often need `fill_down_columns: [0]`

### `nil_return_markers`

Be explicit and copy the actual text seen in the file.

Common examples:

- `Nil Return`
- `Nil return`
- `Nil Return `
- `Nil return all other ministers`

Rows are skipped if any mapped field or the date field contains one of these markers.

### `date_source` and `date_precision`

Use `date_source: "column"` when the sheet has a usable date cell.

Use `date_source: "none"` when:

- the sheet is all nil returns,
- the date column is not meaningful for actual rows,
- the publication period should define the row date range.

Date precision rules:

- `day` for exact dates or parseable date-time values
- `day_or_month` for legacy sheets where the same date column mixes exact days and month values
- `month` for month names or month-year values
- `quarter` when the row only belongs to the publication period

Current extractor supports these common patterns:

- exact ISO dates like `2024-01-10`
- exact ISO datetimes like `2016-07-20T00:00:00`
- exact day strings via `date_format`
- ordinal days like `14th October 2015`
- month names like `October`
- month-year like `December 2015`
- short month-year like `Oct-12`
- mixed legacy values like `Feb-11` and `19-Mar-11` in the same column
- day ranges like `02-06 September`

If a date pattern is not yet supported and is clearly recurring, update code only if needed. Otherwise prefer a schema that reflects the current supported behavior.

## Common Layout Patterns

You will encounter these often:

- modern CSV meetings:
  - `Minister`, `Date`, `Name of organisation or individual`, `Purpose of meeting`
- modern CSV gifts:
  - `Minister`, `Date`, `Gift`, `Given or received`, `Who gift was given to or received from`, `Value (£)`, `Outcome`
- modern CSV hospitality:
  - `Minister`, `Date`, `Person or organisation that offered hospitality`, `Type of hospitality received`, `Accompanied by spouse...`
- modern CSV travel:
  - separate start and end date columns
- older ODS/XLS/XLSX workbooks:
  - `Gifts`, `Hospitality`, `Meetings`, `Overseas_travel`
  - names filled down from the first row in each block
  - helper sheets like `Sheet2`
  - explanatory `Notes`
- special adviser sheets:
  - similar structure but first column is `Special adviser`
- outside employment HTML tables:
  - often one table with person name, role, outside employment text

## Workflow For Creating A New Schema

1. Reproduce the fingerprint.

Use the cached file and the normaliser/fingerprint modules to confirm the sheet fingerprint.

2. Inspect the actual rows around the detected header row.

Do not rely only on the logged preview if the layout is ambiguous.

3. Decide if this is a new schema or should match an existing fingerprint.

If the fingerprint is different, create a new schema file even if the semantic content is similar.

4. Create `schemas/<fingerprint>.json`.

5. Validate it.

At minimum, confirm:

- `load_schema()` finds it
- `validate_schema()` passes on the cached file
- `extract()` returns reasonable rows

6. If the sheet is clearly notes/helper content, prefer `notes` or `ignore` rather than forcing a data schema.

## Validation Commands

Always use `uv`.

Run tests:

```bash
uv run pytest tests/test_gov_transparency_fingerprint.py tests/test_gov_transparency_schema.py tests/test_gov_transparency_extract.py tests/test_gov_transparency_normalise.py tests/test_gov_transparency_crawler.py
```

To inspect partial emitted statements while the crawler is still failing fast on an unknown fingerprint, run:

```bash
uv run muckrake crawl gb_gov_transparency --output - > partial-gov.pack.csv
```

This writes emitted statements to stdout as they are produced, so you can inspect partial output even if the crawl aborts later on an unknown fingerprint.

To inspect a cached file manually, use a short `uv run python -c` snippet that imports:

- `normalise.py`
- `fingerprint.py`
- `schema.py`
- `extract.py`

and prints:

- sheet names
- header row index
- fingerprint
- a few rows around the header
- extracted row count

## Current Known Fingerprints

Some common ones already covered:

- `773032b19673f830`: modern ministerial meetings CSV
- `07c8319eaa992391`: modern ministerial gifts CSV
- `2dfa24ad621f81df`: modern ministerial hospitality CSV
- `58a4996c0fe66d4e`: modern ministerial travel CSV
- `528536782065945f`: special adviser gifts workbook sheet
- `69b6327f9b441d84`: special adviser hospitality workbook sheet
- `4d9adf3bafa88456`: special adviser meetings workbook sheet
- `c798eb99d71af58f`: older ODS gifts sheet
- `94e4bd3d1d76f6ea`: older ODS hospitality sheet
- `7f6dd9c8dc1e2398`: older ODS travel sheet
- `3ba667a4f2110b46`: older ODS meetings sheet
- `e8dae50b9c72457c`: notes sheet
- `24cd6fcfe9fcdc0e`: helper `Sheet2`
- `3f9d5a3e0d18a6c4`: helper `Sheet2` variant

## Constraints

- Crash loudly on ambiguity. Do not guess.
- Prefer minimal schemas.
- Do not introduce new abstractions unless needed.
- Do not edit unrelated datasets.
- Do not commit, push, or open PRs unless explicitly asked.
- Do not emit entities directly when your task is only to add schemas.

## What Good Looks Like

A good schema:

- uses the correct fingerprint
- validates cleanly
- captures real data rows without false positives
- skips nil returns correctly
- uses the narrowest correct date behavior
- does not treat notes/helper sheets as data
