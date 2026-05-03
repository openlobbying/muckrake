# GOV.UK Transparency Mapping Model

## Purpose

This file is the canonical description of the crawler model for `datasets/gb/gov_transparency/`.

It defines:

- supported activity types
- emitted FtM schemata
- intermediate row fields
- date parsing model
- role semantics
- non-data sheet handling

`README.md` gives dataset context. `AGENTS.md` gives operational instructions for adding schemas. This file defines the actual mapping model.

## Intermediate Row Model

The crawler extracts source rows into an intermediate row dict before emitting FtM entities.

Current canonical row fields:

- `official_name`
- `counterparty_name`
- `summary`
- `amount`
- `outcome_text`
- `location`

These are not raw FtM property names. They are source-oriented fields that can map differently by activity type.

## Activity Types

## `meetings`

Emitted primary entity:

- `Meeting`

Supporting context entities:

- `Person`
- `PublicBody`
- `Employment`
- `LegalEntity`

Mapping:

- `official_name` -> `Person.name`
- publication department/context -> `PublicBody.name`
- `counterparty_name` -> `LegalEntity.name` -> `Meeting.involved`
- `summary` -> `Meeting.summary`
- `Person` and `PublicBody` -> `Meeting.organizer`

## `gifts`

Emitted primary entity:

- `Gift`

Supporting context entities:

- `Person`
- `PublicBody`
- `Employment`
- `LegalEntity`

Mapping:

- `official_name` -> `Person.name`
- `counterparty_name` -> `LegalEntity.name` -> `Gift.payer`
- `summary` -> `Gift.purpose`
- `amount` -> `Gift.amount`
- `outcome_text` -> `Gift.description`
- `Person` and `PublicBody` -> `Gift.beneficiary`

## `hospitality`

Emitted primary entity:

- `Hospitality`

Supporting context entities:

- `Person`
- `PublicBody`
- `Employment`
- `LegalEntity`

Mapping:

- `official_name` -> `Person.name`
- `counterparty_name` -> `LegalEntity.name`
- `summary` -> `Hospitality.purpose`
- `amount` -> `Hospitality.amount`
- `outcome_text` -> `Hospitality.notes`

Role mode `default`:

- `LegalEntity` -> `Hospitality.payer`
- `LegalEntity` -> `Hospitality.organizer`
- `LegalEntity` -> `Hospitality.involved`
- `Person` and `PublicBody` -> `Hospitality.beneficiary`

Role mode `hosted_by_official`:

- `Person` and `PublicBody` -> `Hospitality.organizer`
- `LegalEntity` -> `Hospitality.involved`
- no automatic `payer`

This role mode is mainly used for Chequers / official reception style layouts.

## `travel`

Emitted primary entity:

- `Trip`

Supporting context entities:

- `Person`
- `PublicBody`
- `Employment`

Mapping:

- `official_name` -> `Person.name`
- `summary` -> `Trip.summary`
- `location` -> `Trip.location`
- `amount` -> `Trip.notes`
- `Person` and `PublicBody` -> `Trip.involved`

## `outside_employment`

Emitted primary entity:

- `Employment`

Supporting context entities:

- `Person`
- `PublicBody`
- `Employment` for public role context
- `Organization`

Current mapping:

- `official_name` -> `Person.name`
- `counterparty_name` or fallback `summary` -> `Organization.name`
- `summary` -> `Employment.description`

Important caveat:

- not every future outside income / interest table will necessarily fit this model
- extend this activity type carefully, based on real source samples

## Subject Resolution

The subject is configured separately from source column mapping.

Supported subject modes:

- `column`
- `value`
- `provenance`

Use `provenance` when the sheet rows describe guests, receptions, or similar rows where the official person is implied by the attachment title rather than listed in each row.

## Date Model

Dates are configured in schema under `date`.

Supported date modes:

- `none`
- `provenance_period`
- `column`
- `column_range`

For column-based modes, parsing is driven by an ordered list of parser rules.

Supported parser rule types:

- `strptime`
- `excel_serial`
- `iso_datetime`
- `day_range`
- `month_name`
- `month_name_from_period`

Parser rules are tried in order. The first successful rule wins.

This replaces the older `date_source` + `date_precision` + `date_format` pattern.

## Layout Model

Layout settings are grouped under `layout`.

Supported layout fields:

- `data_start_offset`
- `fill_down_columns`
- `skip_row_prefixes`
- `nil_return_markers`

These affect row handling only. They do not define FtM mappings.

## Non-Data Sheets

Supported non-data `sheet_type` values:

- `notes`
- `ignore`

Both require a human-readable `reason` in schema.

These sheets do not emit extracted rows or entities.

## Trace Manifest

The crawler writes a JSONL trace manifest at:

- `data/datasets/gb_gov_transparency/trace/manifest.jsonl`

Current trace records include source-level and sheet-level diagnostics such as:

- provenance URL
- attachment and publication titles
- file format
- sheet name
- detected header row
- normalized header preview
- fingerprint
- schema path
- row counts and skip counts
- emitted entity count

This is the primary mechanism for historical verification and operator debugging.
