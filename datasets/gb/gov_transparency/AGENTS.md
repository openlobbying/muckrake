This directory contains code that crawls and processes UK government transparency publications from GOV.UK, covering ministerial meetings, gifts, hospitality, travel, and more. See `README.md` for dataset context and `MAPPING.md` for the canonical crawler model.

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

Each schema JSON maps to the structured `Schema` dataclass in `schema.py`.

Important top-level fields:

- `fingerprint`: must match the filename and actual computed fingerprint
- `sheet_type`: `data`, `notes`, or `ignore`
- `reason`: required human-readable explanation for `notes` or `ignore` schemas so future work can see why the layout was skipped
- `activity_type`: one of:
  - `meetings`
  - `gifts`
  - `hospitality`
  - `travel`
  - `outside_employment`
  - required for `data` sheets only; omit it for `notes` and `ignore`
- `subject`: subject resolution config
- `layout`: row-handling config
- `date`: date parsing config
- `mapping`: mapping from canonical intermediate field names to source column indexes
- `role_mode`: optional explicit role behavior, currently mainly `hosted_by_official`

Canonical mapping fields currently supported:

- `official_name`
- `counterparty_name`
- `summary`
- `amount`
- `outcome_text`
- `location`

## How To Decide Schema Fields

### `sheet_type`

Use:

- `notes` for explanatory tabs like `Notes`
- `ignore` for helper sheets like `Sheet2` or other non-data layouts with no activity rows
- `data` only for real activity rows

Do not classify a fingerprint as `notes` or `ignore` just because the sampled file is a nil return. If the layout is a genuine activity table that may contain real rows in another publication, keep it as `data` and use nil markers to skip the nil rows.

### `layout.data_start_offset`

Usually `1` because data starts right after the detected header row.

If the header row is followed by a spacer row or a repeated title row, increase it only if necessary.

Very short early CSVs can still confuse header detection. If a two-row or three-row file clearly has the right semantic header but the computed header row lands on a data row, confirm it with the normaliser/fingerprint tools before deciding whether to use a temporary non-default `data_start_offset` or fix the detector.

### `layout.fill_down_columns`

Use this when a workbook lists a minister/adviser once and leaves following rows blank.

Common examples:

- ODS ministerial sheets from older Cabinet Office workbooks often need `fill_down_columns: [0]`
- Some CSV transparency returns also list the minister only on the first row of a block and leave later rows blank; if the data clearly continues under the same person, use `fill_down_columns: [0]`

### `layout.nil_return_markers`

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

### `layout.skip_row_prefixes`

Use this when a sheet contains explanatory or disclaimer rows inside the data area and those rows would otherwise look non-empty enough to be treated as activities.

Be explicit and copy the actual opening text seen in the file.

Common example:

- Chequers hospitality sheets often append a note row beginning `This return includes guests who have received official hospitality at Chequers`

Prefer `skip_row_prefixes` in the schema over dataset-specific code when the rule is a recurring row-text pattern.

### `date`

The crawler now uses a rule-based date model.

Supported date modes:

- `none`
- `provenance_period`
- `column`
- `column_range`

For column-based modes, provide ordered parser rules under `date.parsers`.

Common parser types:

- `strptime`
- `excel_serial`
- `iso_datetime`
- `day_range`
- `month_name`
- `month_name_from_period`

Rules are tried in order. The first successful parser wins.

Use `subject.source: "provenance"` for layouts like Chequers guest lists where the official subject is implied by the attachment title rather than present in a source column.

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

The schema loader is strict: unknown keys and unsupported enum values fail validation.

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
