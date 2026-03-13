## What makes this dataset tricky

The ORCL site is a Salesforce Visualforce application with A4J AJAX controls.

- Search pagination (`Next Page`) is AJAX-driven.
- Quarter selection links in "Previous client lists" are AJAX-driven.
- Some quarter client lists have internal pagination (`Next clients` / `Previous clients`).
- Responses include updated Visualforce viewstate fields that must be reused for follow-up actions.

Direct URL requests are not enough for full extraction; you must simulate these postbacks.

## Current behavior

The crawler currently does all of the following:

1. Crawls search result pages via AJAX `Next Page` postbacks.
2. Loads each profile page.
3. Extracts all quarter snapshots (current + previous links).
4. For each quarter snapshot, follows internal client pagination to collect all clients.
5. Emits `Representation` records with quarter `startDate`/`endDate`.

## Caching: what is cached and what is not

### Cached

- Profile HTML pages are cached via `context.fetch_resource(...)` under:
  - `data/resources/profile_<salesforce_id>.html`
- Extracted quarter snapshots are cached as JSON under:
  - `data/resources/profile_<salesforce_id>_snapshots.json`

This means reruns should avoid re-doing the expensive AJAX workflow for profiles that are already cached.

### Not cached by HTTP layer

- AJAX postbacks (quarter links and next-clients pages) are not directly cached by `fetch_text`/`fetch_json`.
- Instead, their *result* is captured in the snapshots JSON cache above.

If you want a full refresh, delete those snapshot JSON files (or `data/resources/`).

## Key helper functions

- `parse_ajax_submit(onclick)`
  - Parses A4J `onclick` handlers to extract form id + trigger parameter.
- `hidden_inputs_payload(soup)`
  - Rebuilds payload from hidden fields (includes ViewState fields).
- `post_ajax(session, url, payload)`
  - Sends ORCL-compatible AJAX request headers.
- `fetch_all_clients_from_form(...)`
  - Walks `Next clients` pages for a quarter until completion.

## Data caveats

- Some cells include structured text like:
  - `All Party Parliamentary Group on Customer Service`
  - `Funded by`
  - `Institute of Customer Service (ICS)`
- Current parser drops `Funded by` token but still keeps the two meaningful names.
- If ORCL changes table markup, review `extract_clients_from_table` first.

## Safety limits

- `MAX_CLIENT_PAGES = 10` prevents infinite loops in broken pagination.
- If hit, crawler logs a warning and keeps partial data for that quarter.

## If extraction breaks in the future

1. Reproduce with one known profile URL.
2. Capture browser `curl` for the failing click (like `Next clients`).
3. Compare payload fields to `hidden_inputs_payload(...)` output.
4. Confirm `AJAXREQUEST` + trigger parameter pair matches the clicked control.
5. Verify updated ViewState values are present in response and reused on subsequent requests.
