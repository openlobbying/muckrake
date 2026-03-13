import re
import json
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from muckrake.dataset import Dataset
from muckrake.utils import normalize_gb_coh

BASE_URL = "https://orcl.my.site.com"
SEARCH_URL = "https://orcl.my.site.com/CLR_Search"
AJAX_SUBMIT_RE = re.compile(
    r"A4J\.AJAX\.Submit\('([^']+)'.*?'parameters':\{'([^']+)':'([^']+)'\}"
)
AJAX_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Accept": "*/*",
}
MAX_CLIENT_PAGES = 10

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_quarter_range(label: str):
    match = re.match(r"^\s*([A-Za-z]+)\s+to\s+([A-Za-z]+)\s+(\d{4})\s*$", label)
    if not match:
        return None, None

    start_month = MONTHS.get(match.group(1).lower())
    end_month = MONTHS.get(match.group(2).lower())
    year = int(match.group(3))
    if start_month is None or end_month is None:
        return None, None

    start_date = f"{year:04d}-{start_month:02d}"
    end_date = f"{year:04d}-{end_month:02d}"
    return start_date, end_date


def to_month_token(value: str | None):
    if value is None:
        return None
    match = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?$", value)
    if not match:
        return value
    return f"{match.group(1)}-{match.group(2)}"


def parse_ajax_submit(onclick: str):
    match = AJAX_SUBMIT_RE.search(onclick)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def hidden_inputs_payload(soup: BeautifulSoup):
    payload = {}
    for input_tag in soup.find_all("input", type="hidden"):
        name = input_tag.get("name")
        if name:
            payload[name] = input_tag.get("value", "")
    return payload


def post_ajax(session: requests.Session, url: str, payload: dict[str, str]):
    headers = dict(AJAX_HEADERS)
    headers["Referer"] = url
    return session.post(url, data=payload, headers=headers, timeout=60)


def crawl(context: Dataset):
    context.log.info("Starting ORCL live crawl")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
    )

    # Initial Page
    context.log.info(f"Fetching Page 1...")
    res = session.get(SEARCH_URL, timeout=60)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    seen_profiles = set()

    # Process Page 1
    process_page(context, session, soup, page_num=1, seen_profiles=seen_profiles)

    page_num = 1
    while True:
        # Check for Next Page link
        next_page_link = soup.find("a", text="Next Page")
        if not next_page_link:
            context.log.info("No 'Next Page' link found. Finished pagination.")
            break

        onclick = next_page_link.get("onclick")
        if not isinstance(onclick, str):
            context.log.warning("Missing or invalid Next Page click handler. Stopping.")
            break
        parsed = parse_ajax_submit(onclick)
        if parsed is None:
            context.log.warning("Could not parse Next Page click handler. Stopping.")
            break

        container_id, link_id, _ = parsed

        # Prepare Payload
        payload = hidden_inputs_payload(soup)

        payload["AJAXREQUEST"] = "_viewRoot"
        payload[container_id] = container_id
        payload[link_id] = link_id

        page_num += 1
        context.log.info(f"Fetching Page {page_num}...")

        # time.sleep(0.1)  # Be polite

        res = post_ajax(session, SEARCH_URL, payload)
        if res.status_code != 200:
            context.log.error(f"Page {page_num} fetch failed with {res.status_code}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        process_page(
            context,
            session,
            soup,
            page_num=page_num,
            seen_profiles=seen_profiles,
        )


def process_page(
    context: Dataset,
    session: requests.Session,
    soup: BeautifulSoup,
    page_num: int,
    seen_profiles: set[str],
):
    items = extract_list_items(soup)
    context.log.info(f"Page {page_num}: found {len(items)} items")

    processed = 0
    for idx, item in enumerate(items, start=1):
        name = item.get("name")
        profile_url = item.get("profile_url")
        if profile_url in seen_profiles:
            context.log.info(f"Page {page_num}: skipping duplicate profile {name}")
            continue

        seen_profiles.add(profile_url)
        if idx == 1 or idx % 5 == 0 or idx == len(items):
            context.log.info(f"Page {page_num}: processing {idx}/{len(items)} - {name}")
        process_lobbyist(context, session, item)
        processed += 1

    context.log.info(
        f"Page {page_num}: completed {processed} unique profiles (total seen: {len(seen_profiles)})"
    )


def extract_list_items(soup):
    results = []
    table = soup.find("table", class_="clrDataTable")
    if not table:
        return results

    tbody = table.find("tbody")
    if not tbody:
        return results

    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) >= 2:
            name_cell = cols[0]
            link_cell = cols[1]

            name = name_cell.get_text(strip=True)
            link_tag = link_cell.find("a")
            profile_url = ""
            if link_tag:
                href = link_tag.get("href", "")
                if href.startswith("/"):
                    profile_url = BASE_URL + href
                else:
                    profile_url = href

            results.append({"name": name, "profile_url": profile_url})
    return results


def process_lobbyist(context: Dataset, session: requests.Session, item):
    name = item["name"]
    url = item["profile_url"]

    if not url:
        return

    try:
        context.log.info(f"Fetching profile: {name}")
        details_html = None

        profile_id = parse_qs(urlparse(url).query).get("id", [None])[0]
        if profile_id:
            try:
                resource_name = f"profile_{profile_id}.html"
                path = context.fetch_resource(
                    resource_name,
                    url,
                    headers=dict(session.headers),
                )
                with open(path, "r", encoding="utf-8") as fh:
                    details_html = fh.read()
            except Exception as exc:
                context.log.warning(
                    f"Profile cache fetch failed for {name}: {exc}. Falling back to live request."
                )

        if details_html is None:
            res = session.get(url, timeout=60)
            if res.status_code != 200:
                context.log.warning(
                    f"Failed to fetch profile for {name}: {res.status_code}"
                )
                return
            details_html = res.text

        details_soup = BeautifulSoup(details_html, "html.parser")
        details = extract_details(details_soup)

        # Emit Firm
        firm_reg_nr = details["company_number"]

        firm = context.make("LegalEntity")
        firm.id = context.make_id("firm", name, reg_nr=firm_reg_nr, register="GB-COH")
        firm.add("name", name)
        firm.add("jurisdiction", "gb")
        firm.add("topics", "role.lobby")
        firm.add("sourceUrl", url)

        if details["address"]:
            firm.add("address", details["address"])

        if firm_reg_nr:
            firm.add("registrationNumber", f"GB-COH-{normalize_gb_coh(firm_reg_nr)}")

        context.emit(firm)

        # Emit clients and relationships for current and previous quarter snapshots.
        snapshots = None
        snapshot_path = None
        if profile_id:
            snapshot_path = (
                context.resources_path / f"profile_{profile_id}_snapshots.json"
            )
            if snapshot_path.exists():
                try:
                    snapshots = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    context.log.info(f"{name}: loaded cached quarter snapshots")
                except Exception as exc:
                    context.log.warning(
                        f"{name}: failed to read cached snapshots ({exc}), refreshing"
                    )

        if snapshots is None:
            snapshots = collect_quarter_snapshots(context, session, url, details_soup)
            if snapshot_path is not None:
                try:
                    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                    snapshot_path.write_text(
                        json.dumps(snapshots, ensure_ascii=True),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    context.log.warning(
                        f"{name}: failed to write snapshot cache ({exc})"
                    )

        context.log.info(f"{name}: found {len(snapshots)} quarter snapshots")
        for snapshot in snapshots:
            start_date = to_month_token(snapshot.get("start_date"))
            end_date = to_month_token(snapshot.get("end_date"))
            for client_name in snapshot["clients"]:
                client_name = client_name.strip()
                if not client_name:
                    continue

                client = context.make("LegalEntity")
                client.id = context.make_id("client", client_name)
                client.add("name", client_name)
                client.add("jurisdiction", "gb")
                context.emit(client)

                rel = context.make("Representation")
                rel.id = context.make_id(
                    "rel",
                    firm.id,
                    client.id,
                    start_date,
                    end_date,
                )
                rel.add("agent", firm)
                rel.add("client", client)
                rel.add("role", "Lobbyist")
                rel.add("sourceUrl", url)
                rel.add("startDate", start_date)
                rel.add("endDate", end_date)
                context.emit(rel)

    except Exception as e:
        context.log.error(f"Error processing lobbyist {name}: {e}")


def extract_details(soup):
    details = {
        "address": None,
        "company_number": None,
        "clients": [],
        "start_date": None,
        "end_date": None,
    }

    # 1. Address
    # TODO: Add website
    address_h3 = soup.find("h3", string=re.compile(r"Address", re.I))
    if address_h3:
        address_p = address_h3.find_next_sibling("p")
        if address_p:
            # Drop any script tags
            for script in address_p.find_all("script"):
                script.decompose()
            addr_text = address_p.get_text(separator=" ", strip=True)
            details["address"] = addr_text

    # 2. Company Number
    company_label = soup.find("label", string=re.compile(r"Company Number", re.I))
    if company_label:
        next_sibling = company_label.next_sibling
        if next_sibling and isinstance(next_sibling, str) and next_sibling.strip():
            details["company_number"] = next_sibling.strip()
        else:
            # Fallback
            text = (
                company_label.get_text(strip=True).replace("Company Number", "").strip()
            )
            if text:
                details["company_number"] = text

    # 3. Current quarter metadata
    period_label, start_date, end_date, clients_form = extract_current_quarter_metadata(
        soup
    )
    if period_label:
        details["start_date"] = start_date
        details["end_date"] = end_date
        details["clients"] = (
            extract_clients_from_container(clients_form) if clients_form else []
        )

    return details


def extract_current_quarter_metadata(soup):
    heading = soup.find(string=re.compile(r"Current client list", re.I))
    if not heading:
        return None, None, None, None

    heading_text = heading.strip()
    period_match = re.search(r"Current client list\s*\(([^)]+)\)", heading_text, re.I)
    if not period_match:
        return None, None, None, None

    period_label = period_match.group(1).strip()
    start_date, end_date = parse_quarter_range(period_label)
    clients_form = heading.find_next("form")
    return period_label, start_date, end_date, clients_form


def extract_clients_from_table(table):
    clients = []
    seen = set()
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        value_col = cols[-1]
        for token in value_col.stripped_strings:
            token = token.strip()
            if not token or token.lower() in ("client", "funded by"):
                continue
            if token in seen:
                continue
            seen.add(token)
            clients.append(token)
    return clients


def extract_clients_from_container(container):
    clients = []
    seen = set()
    for table in container.find_all("table", class_="clrDataTable"):
        for client_name in extract_clients_from_table(table):
            if client_name in seen:
                continue
            seen.add(client_name)
            clients.append(client_name)
    return clients


def fetch_all_clients_from_form(
    context: Dataset,
    session: requests.Session,
    profile_url: str,
    page_soup: BeautifulSoup,
    clients_form,
):
    if clients_form is None:
        return []

    seen = set()
    clients = []
    pages = 0

    while clients_form is not None and pages < MAX_CLIENT_PAGES:
        pages += 1
        for client_name in extract_clients_from_container(clients_form):
            if client_name in seen:
                continue
            seen.add(client_name)
            clients.append(client_name)

        next_link = clients_form.find("a", text=re.compile(r"Next clients", re.I))
        if not next_link:
            break

        onclick = next_link.get("onclick")
        if not isinstance(onclick, str):
            break

        parsed = parse_ajax_submit(onclick)
        if parsed is None:
            break

        form_id, trigger_name, trigger_value = parsed

        payload = hidden_inputs_payload(page_soup)

        payload["AJAXREQUEST"] = "_viewRoot"
        payload[form_id] = form_id
        payload[trigger_name] = trigger_value

        response = post_ajax(session, profile_url, payload)
        if response.status_code != 200:
            break

        page_soup = BeautifulSoup(response.text, "html.parser")
        clients_form = page_soup.find("form", id=form_id)

    if pages >= MAX_CLIENT_PAGES:
        context.log.warning(
            f"{profile_url}: reached max client page limit ({MAX_CLIENT_PAGES})"
        )
    elif pages > 1:
        context.log.info(f"{profile_url}: paged clients across {pages} pages")
    return clients


def collect_quarter_snapshots(
    context: Dataset, session: requests.Session, profile_url: str, soup: BeautifulSoup
):
    snapshots = []
    seen_periods = set()

    def append_snapshot(snapshot_soup):
        period_label, start_date, end_date, clients_form = (
            extract_current_quarter_metadata(snapshot_soup)
        )
        if not period_label or period_label in seen_periods:
            return
        clients = fetch_all_clients_from_form(
            context,
            session,
            profile_url,
            snapshot_soup,
            clients_form,
        )
        if not clients:
            return
        seen_periods.add(period_label)
        snapshots.append(
            {
                "period_label": period_label,
                "clients": clients,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    append_snapshot(soup)

    previous_links = soup.find_all(
        "a", onclick=re.compile(r"A4J\.AJAX\.Submit\('j_id0:j_id1:previousReturns:")
    )
    context.log.info(
        f"{profile_url}: fetching {len(previous_links)} previous quarter links"
    )
    for link in previous_links:
        onclick = link.get("onclick")
        if not isinstance(onclick, str):
            continue

        parsed = parse_ajax_submit(onclick)
        if parsed is None:
            continue

        form_id, trigger_name, trigger_value = parsed

        payload = hidden_inputs_payload(soup)

        payload["AJAXREQUEST"] = form_id
        payload[form_id] = form_id
        payload[trigger_name] = trigger_value

        # time.sleep(0.1)
        response = post_ajax(session, profile_url, payload)
        if response.status_code != 200:
            context.log.warning(
                f"Failed to fetch previous client list for {profile_url} ({response.status_code})"
            )
            continue

        response_soup = BeautifulSoup(response.text, "html.parser")
        period_label = link.get_text(" ", strip=True)
        if not period_label or period_label in seen_periods:
            continue

        clients_span_id = re.sub(r":j_id166$", ":clients", form_id)
        clients_span = response_soup.find(id=clients_span_id)
        clients = []
        if clients_span:
            span_form = clients_span.find("form")
            clients = fetch_all_clients_from_form(
                context,
                session,
                profile_url,
                response_soup,
                span_form,
            )

        if not clients:
            continue

        start_date, end_date = parse_quarter_range(period_label)
        seen_periods.add(period_label)
        snapshots.append(
            {
                "period_label": period_label,
                "clients": clients,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return snapshots
