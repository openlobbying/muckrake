### GOV.UK Ministerial Transparency

This directory now contains a shared GOV.UK crawler for:

- meetings
- gifts
- hospitality
- overseas travel

The implementation is intentionally simple:

- discover publication pages from one or more GOV.UK collection URLs
- fetch CSV and Excel attachments only
- normalize inconsistent headers and repeated minister sections
- emit raw ministerial records into one FollowTheMoney dataset

It does **not** try to split multi-attendee cells. Each meeting participant cell is currently imported as a single raw `LegalEntity` so we preserve source text without adding parsing complexity yet.

Shared code:

- `datasets/gb/meetings/common.py`
- `datasets/gb/meetings/crawler.py`
- `datasets/gb/meetings/govuk_ministerial.py`
- `datasets/gb/meetings/config.yml`

Current starter departments in `config.yml`:

- `HM Treasury`
- `Department for Transport`
- `Department for Energy Security and Net Zero`

HM Treasury uses both the historical and current GOV.UK collection pages because HMT moved meetings/travel to a newer collection from late 2024 onwards.

Configuration lives at the top level of this dataset config as a `departments:` list, and `crawler.py` iterates those GOV.UK collection URLs into one unified `meetings` dataset.

Reference list of GOV.UK departmental transparency pages:

https://www.gov.uk/search/transparency-and-freedom-of-information-releases?parent=/government/government-efficiency-transparency-and-accountability&keywords=meeting&topic=f3f4b5d3-49c4-487b-bd5b-be75f11ec8c5&content_store_document_type%5B%5D=transparency&order=updated-newest
