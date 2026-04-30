This directory contains code that crawls and processes UK government transparency publications from GOV.UK, covering ministerial meetings, gifts, hospitality, travel, and more. See the README.md for more details.

The code covers several stages:

- Discovery via the GOV.UK Content API
- Normalisation into `NormalisedSheet`. This ensures we have a consistent internal representation of sheets across CSV, XLSX, ODS, and HTML sources.
- Each sheet gets a stable structural fingerprint based on its header row and column structure.
- We look up the fingerprint in our known schemas. If it's unknown, we log a preview and provenance for manual inspection.
- You job as an AI agent is to create new schema JSON files for unknown fingerprints in `schemas/`.

## Your Job

When the crawler reports `UNKNOWN FINGERPRINT: <fingerprint>`, you are to:

1. Run `uv run muckrake crawl gb_gov_transparency` to crawl the dataset. It will likely produce an "UNKNOWN FINGERPRINT" error with a preview of the sheet and its provenance.
2. Find the matching cached source file in `data/datasets/gb_gov_transparency/resources/`.
3. Confirm the actual header row and data rows.
4. Decide whether the sheet is:
   - `data`
   - `notes`
   - `ignore` (explain why you are ignoring it to the user)
5. Create a `schemas/<fingerprint>.json`.
6. Run the crawler (`uv run crawl gb_gov_transparency`) again to validate the schema.
7. If you encounter a new unknown fingerprint, repeat the process. Do not stop this loop until the user tells you to stop or focus on something else.

## Schema Format

Each schema JSON maps to the `Schema` dataclass in `schema.py`.

Important fields:

- `fingerprint`: must match the filename and actual computed fingerprint
- `sheet_type`: `data`, `notes`, or `ignore`
- `reason`: optional human-readable explanation for `notes` or `ignore` schemas so future work can see why the layout was skipped
- `activity_type`: one of:
  - `meetings`
  - `gifts`
  - `hospitality`
  - `travel`
  - `outside_employment`
  - `other`
  - required for `data` sheets only; omit it for `notes` and `ignore`
- `data_start_offset`: usually `1`
- `fill_down_columns`: columns where blanks mean “same as row above”
- `nil_return_markers`: markers that mean the row is not a real activity
  - optional for `data` sheets because common nil-return markers are applied automatically
- `skip_row_prefixes`: optional leading-text markers for explanatory rows embedded inside data sheets that should always be skipped
- `reverse_roles`: optional boolean for data layouts where the official/public body hosts or organizes the activity and the counterpart should be `involved` rather than `payer`/`organizer`
- `date_source`:
  - `column`
  - `none`
- `date_column`: required if `date_source == "column"`
- `end_date_column`: optional second date column for layouts with explicit start/end dates
- `date_format`: only for day-level column dates when a fixed `strptime` format is valid
- `date_precision`:
  - `day`
  - `day_or_month`
  - `month`
  - `quarter`
- `columns`: mapping from canonical field names to source column indexes

Canonical fields currently supported:

- required for `data`: `subject_name`
- optional: `counterpart_name`, `activity_description`, `amount`, `outcome`, `location`

## How To Decide Schema Fields

### `sheet_type`

Use:

- `notes` for explanatory tabs like `Notes`
- `ignore` for helper sheets like `Sheet2` or other non-data layouts with no activity rows
- `data` only for real activity rows

Do not classify a fingerprint as `notes` or `ignore` just because the sampled file is a nil return. If the layout is a genuine activity table that may contain real rows in another publication, keep it as `data` and use nil markers to skip the nil rows.

### `data_start_offset`

Usually `1` because data starts right after the detected header row.

If the header row is followed by a spacer row or a repeated title row, increase it only if necessary.

### `fill_down_columns`

Use this when a workbook lists a minister/adviser once and leaves following rows blank.

Common examples:

- ODS ministerial sheets from older Cabinet Office workbooks often need `fill_down_columns: [0]`
- Some CSV transparency returns also list the minister only on the first row of a block and leave later rows blank; if the data clearly continues under the same person, use `fill_down_columns: [0]`

### `nil_return_markers`

Be explicit and copy the actual text seen in the file.

Data sheets already inherit common nil-return markers such as `Nil Return`, `Nil return`, `Nil Return `, `Nil return all other ministers`, and `None in this period`.

Only add `nil_return_markers` in the schema when a source uses extra text beyond those defaults.

A nil-only publication can still use a `data` schema if the underlying layout is a real activity table.

Common examples:

- `Nil Return`
- `Nil return`
- `Nil Return `
- `Nil return all other ministers`

Rows are skipped if any mapped field or the date field contains one of these markers.

### `skip_row_prefixes`

Use this when a sheet contains explanatory or disclaimer rows inside the data area and those rows would otherwise look non-empty enough to be treated as activities.

Be explicit and copy the actual opening text seen in the file.

Common example:

- Chequers hospitality sheets often append a note row beginning `This return includes guests who have received official hospitality at Chequers`

Prefer `skip_row_prefixes` in the schema over dataset-specific code when the rule is a recurring row-text pattern.

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

Edge case tips:

- Some fingerprints are shared by files where the same logical date column alternates between exact days and month-level values. Prefer `date_precision: "day_or_month"` if the same layout is used for both.
- Some travel rows use a single date column with day ranges like `3-4 April 2017`. Treat these as a single `date_column` with `date_precision: "day"`; extraction can emit a start/end date range.
- Nil-only sheets sometimes leave the date and other fields blank and put the nil marker only in one mapped field. In those cases keep the sheet as `data`, add the exact `nil_return_markers` text seen in the file, and use `date_source: "none"` if there is no usable date cell.
- A few malformed wide CSVs cause header detection to land on the first nil-return row instead of the actual header line. If the real data rows are still unambiguous, it is acceptable to use a non-default `data_start_offset`, including a negative offset, to recover the true data region for that fingerprint.

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

If you classify a schema as `notes` or `ignore`, add a `reason` field that explains why it is being skipped.

5. Validate it.

At minimum, confirm:

- `load_schema()` finds it
- `validate_schema()` passes on the cached file
- `extract()` returns reasonable rows

If extraction includes embedded explanatory text as a fake record, add `skip_row_prefixes` to the schema and revalidate.

6. If the sheet is clearly notes/helper content, prefer `notes` or `ignore` rather than forcing a data schema.

Do not use `notes` or `ignore` for data layouts that only happen to be nil returns in the sampled file.

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

## Constraints

- Crash loudly on ambiguity. Do not guess.
- Prefer minimal schemas.
- Do not introduce new abstractions unless needed.
- Do not edit unrelated datasets.
- Do not commit, push, or open PRs unless explicitly asked.
- Do not emit entities directly when your task is only to add schemas.
