# Transparency File Examples

This document records real examples of tabular transparency files encountered in the current `config.yml` source list. The goal is to show the range of file formats and layout patterns that a parser needs to handle.

The examples below were gathered from live GOV.UK publication metadata and sample file contents.

## Format mix observed

Across the current configured collection list:

- `8,810` attachments have a `.csv` filename
- `287` attachments have a `.xlsx` filename
- `225` attachments have a `.ods` filename
- `64` attachments have a `.xls` filename
- `27` attachments have a `.xlsm` filename
- `25` attachments are HTML publications containing tabular data

Important caveat:

- Some older files are served with Excel MIME types but are actually CSV files.
- File extension is more reliable than MIME type, but both can be wrong.

## High-level patterns

The examples below include these recurring structures:

- Single clean CSV table with a single header row
- CSVs with one file per activity type
- CSVs with one file per person and per activity type
- Old CSVs with month-level dates like `Oct-12`
- CSVs where rows are explicit `Nil Return`
- Workbooks with multiple sheets such as `Gifts`, `Hospitality`, `Meetings`, `Travel`
- Workbooks with a `Notes` sheet describing the meaning of the other sheets
- Workbooks where person names appear once and are blank on following rows
- Workbooks mixing exact dates, month names, and date ranges in one column
- Workbooks with unused helper sheets like `Sheet2`
- HTML publications with proper `<table>` markup
- HTML publications whose table represents a different transparency dataset type such as outside employment

## Example 1: Simple modern meetings CSV

- Publication: `DfT: ministerial gifts, hospitality, travel and meetings, January to March 2024`
- File: `https://assets.publishing.service.gov.uk/media/66d0532f1df0ac810b1f84a1/dft-ministerial-external-meetings-january-to-march-2024.csv`
- Type: `.csv`

Observed structure:

- Single table
- Header row at the top
- One event per row
- Exact dates in `dd/mm/yyyy`
- Counterpart column is named `Name of Individual or Organisation`

Sample header:

```text
Minister,Date,Name of Individual or Organisation,Purpose of Meeting
```

Quirks:

- Counterpart values may contain multiple organizations in one cell
- Purpose fields can be long free text
- Some counterpart cells include URLs inline

## Example 2: Similar CSV, different header wording and date format

- Publication: `Cabinet Office: ministerial gifts, hospitality, travel and meetings, January to March 2023`
- File: `https://assets.publishing.service.gov.uk/media/64b7fc1a2059dc000d5d25f5/Cabinet_Office_ministerial_meetings__January_to_March_2023.csv`
- Type: `.csv`

Observed structure:

- Single table
- Very similar to Example 1
- Exact dates in ISO format `yyyy-mm-dd`
- Counterpart header changes to `Name of organisation or individual`

Sample header:

```text
Minister,Date,Name of organisation or individual,Purpose of meeting
```

Quirks:

- Extra whitespace around names and values
- Smart quotes and typographic punctuation appear in values
- Nil returns can appear as ordinary rows rather than as missing data

## Example 3: Older CSV with month-level dates

- Publication: `Ministerial gifts, hospitality, travel and meetings with external organisations, October to December 2012`
- File: `https://assets.publishing.service.gov.uk/media/5a7b2813e5274a34770e9cf0/comeetingsoct-dec.csv`
- Type: `.csv`

Observed structure:

- Single table
- Header row at the top
- Date values like `Oct-12` rather than exact event dates
- Minister names are long role strings rather than simple names

Sample header:

```text
Minister,Date,Name of Organisation,Purpose of meeting
```

Quirks:

- Date precision is month-level, not day-level
- `Minister` contains both role and name in one field
- Header capitalization changes again

## Example 4: CSVs with every row as `Nil Return`

- Publication: `DfE: special advisers’ gifts, hospitality and meetings, January to March 2024`
- Files:
- `https://assets.publishing.service.gov.uk/media/66d9869de87ad2f1218264c3/DfE_2024_SpAd_Transparency_return__Q1_January_-_March__Gifts.csv`
- `https://assets.publishing.service.gov.uk/media/66d986bffb86ba5a1f214e5d/DfE_2024_SpAd_Transparency_return__Q1_January_-_March__Hospitality.csv`
- Type: `.csv`

Observed structure:

- Valid header row
- One row per adviser
- Every value in the row may be `Nil Return`

Sample gifts content:

```text
Special Adviser,Date,Gift,Who gift was received from,Value (�),Outcome
Lawrence Abel,Nil Return,Nil Return,Nil Return,Nil Return,Nil Return
Jamie Monteith-Mann,Nil Return,Nil Return,Nil Return,Nil Return,Nil Return
```

Quirks:

- Nil return is expressed as data rows, not metadata
- There is an encoding issue in `Value (£)` in the sampled file
- A parser must not treat these as real events

## Example 5: Mixed real rows and nil-return rows in one CSV

- Publication: `DfE: special advisers’ gifts, hospitality and meetings, January to March 2024`
- File: `https://assets.publishing.service.gov.uk/media/66d9aa71293afcbf8a811116/DfE_2024_SpAd_Transparency_return__Q1_January_-_March__Meetings_.csv`
- Type: `.csv`

Observed structure:

- Some advisers have real meetings
- Others are represented by `Nil Return` rows in the same table

Sample content:

```text
Special Adviser,Date,Name of senior media figure,Purpose of meeting
Lawrence Abel,24/01/2024,"Nick Jackson, Louise Turner (Producers, Channel 4 News)",To discuss the Department for Education's priorities and Special Educational Needs and Disabilities (SEND)
Jamie Monteith-Mann,Nil Return,Nil Return,Nil Return
```

Quirks:

- Real and nil-return records coexist
- Counterparts may contain multiple named people and role descriptions in one field

## Example 6: True old Excel `.xls` workbook with multiple sheets

- Publication: `Cabinet Office: special advisers' gifts, hospitality and meetings, April - June 2016`
- File: `https://assets.publishing.service.gov.uk/media/5a74f67440f0b6360e47240a/Special_Adviser_Gifts_and_Hospitality_Apr-Jun_2016__004___Updated_.xls`
- Type: `.xls`

Observed sheet names:

- `Notes`
- `Gifts`
- `Hospitality`
- `Meetings`
- `Sheet2`

Observed structure:

- Separate sheets for each activity type
- `Notes` sheet explains the dataset semantics
- `Sheet2` appears to be a helper/reference sheet, not event data

Notable quirks:

- `Gifts` includes a real row, a blank row, and a summary row: `Nil return from all other special advisers`
- `Meetings` only puts the adviser name in the first row, then leaves the column blank for subsequent rows
- Dates in the workbook are actual spreadsheet dates
- A parser must fill down adviser names in the `Meetings` sheet

Sample `Meetings` rows:

```text
Special adviser | Date | Name | Media organisation represented | Purpose of meeting
Craig Oliver | 2016-04-27 | Jason Beattie | The Mirror | Catch up meeting
"" | 2016-04-29 | Tom McTague | Politico | Catch up meeting
```

## Example 7: `.xlsx` workbook with notes plus dedicated activity sheets

- Publication: `Cabinet Office: special advisers' gifts, hospitality and meetings, October to December 2015`
- File: `https://assets.publishing.service.gov.uk/media/5a81914640f0b62302698020/CO_Special_Adviser_Oct_-_Dec_2015_xls.xlsx`
- Type: `.xlsx`

Observed sheet names:

- `Notes`
- `Gifts`
- `Hospitality`
- `Meetings`
- `Sheet2`

Observed structure:

- Same basic shape as the `.xls` example, but modern workbook format
- `Gifts` is all nil returns
- `Hospitality` contains month names such as `October` and `November` instead of exact dates

Notable quirks:

- Different sheets inside the same workbook may use different date precision
- `Notes` sheet contains useful semantics that may help classify each sheet
- `Sheet2` is a non-data helper sheet

## Example 8: `.xlsm` workbook with macros but ordinary tabular sheets

- Publication: `BEIS: special advisers' gifts, hospitality and meetings, October to December 2016`
- File: `https://assets.publishing.service.gov.uk/media/5a74a5a9e5274a56317a6010/october_december_2016_bis_publications_special_adviser_final.xlsm`
- Type: `.xlsm`

Observed sheet names:

- `Notes`
- `Gifts`
- `Hospitality`
- `Meetings`
- `Sheet2`

Observed structure:

- Closely resembles the Cabinet Office special adviser workbook layout
- In the sampled workbook, multiple sheets are entirely nil returns

Notable quirks:

- Macro-enabled workbook format does not necessarily mean unusual table structure
- A parser should treat `.xlsm` primarily as a workbook container, not as a special semantic case

## Example 9: `.ods` workbook with many activity sheets in one file

- Publication: `Cabinet Office: ministerial gifts, hospitality, travel and meetings, July to September 2016`
- File: `https://assets.publishing.service.gov.uk/media/5a80d8ebe5274a2e8ab52807/prime_minister_quarterly_returns_july_to_september_2016.ods`
- Type: `.ods`

Observed sheet names:

- `Gifts`
- `Hospitality`
- `Overseas_travel`
- `Meetings`
- `Sheet2`
- `GUESTS_AT_CHEQUERS`
- `UK_OFFICIAL_VISITS`
- `OFFICIAL_RECEPTIONS`

Observed structure:

- One workbook contains multiple different transparency datasets
- Some sheets are conventional ministerial returns
- Other sheets are related but distinct publication types such as Chequers guests and official receptions

Notable quirks:

- The same workbook can contain multiple logical datasets, not just multiple sheets for the same dataset
- Person names appear once and are blank on following rows
- A sheet may start with a named minister row followed by a blank row of actual data for that minister
- `Overseas_travel` mixes exact dates and text ranges like `02-06 September`
- `Hospitality` includes both real rows and a `Nil Return` row for another minister in the same sheet

Sample `Overseas_travel` header:

```text
Minister | Date(s) of trip | Destination | Purpose of trip | Mode of transport | Cost of private jet or RAF plane hire, if relevant (£) | Number of officials who accompanied minister if non-scheduled travel was used | Accompanied by spouse, family member(s) or friend at public expense? | Total cost (for minister only) including all visas, accommodation, travel, meals etc (£)
```

## Example 10: HTML publication with proper table markup for meetings

- Publication: `HMRC officials' meetings with tobacco stakeholders, January to March 2025`
- HTML page: `https://www.gov.uk/government/publications/hmrc-officials-meetings-with-tobacco-stakeholders-january-to-march-2025/hmrc-policy-meetings-with-tobacco-stakeholders-january-to-march-2025`
- Type: HTML publication

Observed structure:

- The table is embedded directly in the HTML publication body
- The page contains section headings above separate tables
- One publication may contain multiple tables for related subcategories

Observed columns:

- `Date of meeting`
- `HMRC officials`
- `Organisation`
- `Industry officials’ titles`
- `Issues discussed`

Notable quirks:

- This is not a downloadable CSV or workbook
- The second table in the page repeats header-like rows in the body rather than using a proper `<thead>`
- Section headings carry important context such as stakeholder category

## Example 11: HTML publication with proper table markup for outside employment

- Publication: `HMRC: senior officials’ outside employment, April 2024 to March 2025`
- HTML page: `https://www.gov.uk/government/publications/hmrc-senior-officials-outside-employment-april-2024-to-march-2025/hmrc-senior-officials-outside-employment-april-2024-to-march-2025`
- Type: HTML publication

Observed structure:

- Single HTML table in the body
- No file attachment to download
- Different transparency topic from meetings/gifts/travel, but still clearly tabular

Observed columns:

- `Name of SCS`
- `Role in HMRC`
- `Outside employment`

Notable quirks:

- Outside employment values can contain multiple roles separated by semicolons
- A parser should not assume every HTML table is a meetings dataset

## Example 12: One publication with many small files rather than one combined file

- Publication: `Cabinet Office: ministerial gifts, hospitality, travel and meetings, January to March 2023`
- Example files from the same publication:
- `Rt Hon Rishi Sunak MP meetings, January to March 2023`
- `Rt Hon Rishi Sunak MP official visits, January to March 2023`
- `Leader of the House of Commons and Whips’ ministerial meetings, January to March 2023`
- `Cabinet Office ministerial meetings, January to March 2023`

Observed structure:

- One publication page can expose dozens of small attachment files
- Different people and sub-units have their own files
- The publication title alone is not enough to identify the subject person for each attachment

Notable quirks:

- Subject person or office often needs to be inferred from the attachment title or filename
- The dataset is logically one quarterly release but physically split into many files

## Example 13: Misleading MIME type versus actual content

Example:

- `https://assets.publishing.service.gov.uk/media/5a7e2a5940f0b6230268996e/AGO_hospitality_Oct_-_Dec_13.csv`

Observed behavior:

- GOV.UK metadata may label a `.csv` file with the content type `application/vnd.ms-excel`
- The actual file is still CSV text

Implication for parsing:

- Parser dispatch should inspect filename, content type, and possibly file signature rather than trusting any single source

## Example 14: Helper and notes sheets that are not event data

Observed in multiple workbook examples:

- `Notes`
- `Sheet2`

Observed behavior:

- `Notes` usually contains narrative definitions of gifts, hospitality, or meetings
- `Sheet2` may contain lookup values such as transport types or outcome labels
- These sheets are useful context but should not be emitted as event rows

Implication for parsing:

- The parser should classify sheets before treating them as tables to normalize

## Example 15: Repeated or implicit person context in workbooks

Observed in `.xls` and `.ods` examples:

- First row names the minister or adviser
- Following rows leave the person column blank
- A later row may switch to a new named person or a `Nil Return`

Implication for parsing:

- Fill-down behavior is required
- Blank cells do not necessarily mean missing data; they can mean “same as above”

## Example 16: Multiple logical dataset types inside one source file

Observed in the `.ods` Prime Minister workbook:

- `Gifts`
- `Hospitality`
- `Overseas_travel`
- `Meetings`
- `GUESTS_AT_CHEQUERS`
- `UK_OFFICIAL_VISITS`
- `OFFICIAL_RECEPTIONS`

Implication for parsing:

- The parser cannot assume one file equals one output table or one activity type
- Sheet-level classification is required before normalization

## Example 17: Mixed date precision within the same corpus

Examples observed:

- Exact dates: `18/01/2024`
- ISO dates: `2023-01-12`
- Month values: `October`
- Month-year values: `Oct-12`
- Date ranges: `02-06 September`
- Nil-return markers in date columns: `Nil Return`

Implication for parsing:

- Date parsing needs `raw_date`, normalized date fields, and explicit date precision
- Exact event dates cannot be assumed to exist
- Some legacy CSV families mix month-level and day-level values in the same column, so schema handling must allow per-row precision in those cases

## Example 18: Free-text multi-entity counterpart fields

Examples observed:

- Multiple organizations in one cell separated by commas
- Multiple named individuals with titles and employers in one cell
- Semicolon-delimited lists in outside employment fields

Implication for parsing:

- Parsers should preserve the raw counterpart text exactly
- Splitting individual organizations or people should be a later enrichment step, not a destructive parse-time transformation

## Summary of parser requirements implied by these examples

Any robust parser for this corpus needs to handle:

- CSV, `.xls`, `.xlsx`, `.xlsm`, `.ods`, and HTML table sources
- Misleading MIME types
- Multi-sheet workbooks
- Non-data helper sheets
- One file containing multiple logical datasets
- Publication-level releases split into many small files
- Fill-down context for person names
- Blank spacer rows and summary rows
- Mixed real-event rows and nil-return rows
- Multiple date formats and date precisions
- Evolving header names for the same semantic fields
- Extra columns that only appear in certain departments or topics

These examples are a strong argument for a parser architecture that first detects table structure and context, and only then maps rows into a shared event schema.

## Current schema conventions

- `activity_type` is required for `data` sheets and should be omitted for `notes` and `ignore` sheets.
- `nil_return_markers` is optional for `data` sheets because common markers are applied by default in code.
- Only include `nil_return_markers` in a schema file when a source uses extra source-specific text beyond those defaults.
