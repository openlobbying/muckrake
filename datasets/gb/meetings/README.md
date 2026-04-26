### GOV.UK Ministerial Transparency

This directory contains a shared GOV.UK crawler for:

- meetings
- gifts
- hospitality
- overseas travel

The implementation is intentionally simple:

- discover publication pages from one or more GOV.UK collection URLs
- fetch CSV and Excel attachments only
- normalize inconsistent headers and repeated minister sections
- emit raw ministerial records into one FollowTheMoney dataset

It does **not** try to split multi-attendee cells. Each meeting participant cell is imported as a single raw `LegalEntity` so we preserve source text without adding parsing complexity.

Shared code:

- `datasets/gb/meetings/common.py`
- `datasets/gb/meetings/crawler.py`
- `datasets/gb/meetings/govuk_ministerial.py`
- `datasets/gb/meetings/validation.py`
- `datasets/gb/meetings/config.yml`

Configuration lives at the top level of this dataset config as a `departments:` list, and `crawler.py` iterates those GOV.UK collection URLs into one unified `meetings` dataset.

### Validation logging

The crawler now logs source-level validation at crawl time:

- unknown attachment or sheet categories
- weak field mappings
- attachment read errors
- empty tables
- sources with zero canonical records
- sources with zero emitted records
- a final summary with aggregate counts

For targeted cleanup, the crawler also supports:

- `MUCKRAKE_MEETINGS_DEPARTMENT=<department name>`

Example:

```bash
MUCKRAKE_MEETINGS_DEPARTMENT='Cabinet Office' PYTHONPATH=. uv run muckrake crawl meetings --clear
```

### Current status

- Unified `meetings` dataset is in place.
- Department coverage in `config.yml` has been expanded substantially.
- Meeting date handling has been hardened and the current date audit is at `missing_events=0`.
- Validation logging has been added so import coverage issues show up during crawl, not only in ad hoc scripts.

### Current work log

- Added crawl-time validation in `datasets/gb/meetings/validation.py`.
- Wired validation into source discovery and record emission.
- Added `MUCKRAKE_MEETINGS_DEPARTMENT` filtering for one-department-at-a-time cleanup.
- Started department-by-department cleanup with `Cabinet Office`.

Cabinet Office first pass findings:

- Some warnings are expected out-of-scope attachments:
  - `official visits`
  - `official and charity receptions`
  - `Chequers` / `Chevening` guest lists
- Some warnings look like real parser gaps:
  - legacy travel files using headers like `date of trip`
  - legacy gift files using `date received`
  - legacy files with unusual but still relevant column layouts
- Some zero-emitted sources may be true nil-return style files and need separating from actual import failures.

Cabinet Office second pass changes:

- Added header-first category resolution so obvious header layouts can override misleading file names or titles.
- Added more legacy aliases for:
  - `date received`
  - `date of trip`
  - `purpose`
  - old transport / total-cost column variants
- Added normalization for stacked single-column media CSV layouts.
- Downgraded clearly out-of-scope attachments to informational logs:
  - `official visits`
  - `official and charity receptions`
  - `Chequers` / `Chevening` guest lists
- Downgraded pure nil-return sources from warning-level `zero emitted` failures to informational logs.

Cabinet Office validation summary after second pass:

- `sources=921`
- `unknown_categories=44`
- `ignored_unknown_categories=84`
- `weak_field_mappings=53`
- `zero_canonical=15`
- `zero_emitted=19`

This is materially better than the first pass summary:

- `sources=893`
- `unknown_categories=156`
- `weak_field_mappings=58`
- `zero_canonical=16`
- `zero_emitted=235`

Remaining Cabinet Office issue buckets:

- still-unclassified `UK visits` style files
- some residual weak legacy layouts that may still need source-specific handling
- some residual zero-emitted sources that are not nil returns and should be inspected individually

### Next steps

- Finish the remaining `Cabinet Office` warning buckets, starting with `UK visits` and residual zero-emitted sources.
- Once `Cabinet Office` is in a good state, move to the next department and repeat.

### Operator notes

- Use the validation logs as the primary crawl-time signal.
- Keep the date audit as the semantic backstop:

```bash
uv run scripts/check_meetings_missing_dates.py
```

- Keep changes small and specific to observed source patterns.

Reference list of GOV.UK departmental transparency pages:

https://www.gov.uk/search/transparency-and-freedom-of-information-releases?parent=/government/government-efficiency-transparency-and-accountability&keywords=meeting&topic=f3f4b5d3-49c4-487b-bd5b-be75f11ec8c5&content_store_document_type%5B%5D=transparency&order=updated-newest
