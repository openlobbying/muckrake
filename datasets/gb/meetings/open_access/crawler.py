import csv
from datetime import datetime
from typing import Optional
from muckrake.dataset import Dataset
from muckrake.util import parse_date

BASE_MEETING_URL = "https://openaccess.transparency.org.uk/?meeting="


def crawl_row(dataset: Dataset, row):
    record_id = str(row.get("RecordId") or "").strip()
    if record_id.endswith(".0"):
        record_id = record_id[:-2]
    if not record_id:
        return

    rep_name = row.get("rep_new")
    if not rep_name:
        return

    # Organizations (LegalEntity)
    org_names = row.get("organisation")
    orgs = []
    if org_names:
        name = org_names.strip()
        if name and len(name) >= 3:
            org = dataset.make("LegalEntity")
            org.id = dataset.make_id("org", name)
            org.add("name", name)
            org.add("jurisdiction", "gb")
            dataset.emit(org)
            orgs.append(org)

    # Department (PublicBody)
    dept_name = row.get("department")
    dept = None
    if dept_name:
        dept = dataset.make("PublicBody")
        dept.id = dataset.make_id("dept", dept_name)
        dept.add("name", dept_name)
        dept.add("jurisdiction", "gb")
        dataset.emit(dept)

    # Representative (Person)
    rep = dataset.make("Person")
    rep.id = dataset.make_id("rep", rep_name)
    rep.add("name", rep_name)
    rep.add("jurisdiction", "gb")
    rep.add('topics', 'role.pep')
    dataset.emit(rep)

    if dept:
        employment = dataset.make("Employment")
        employment.id = dataset.make_id(rep.id, dept.id)
        employment.add("employee", rep)
        employment.add("employer", dept)
        dataset.emit(employment)

    # Meeting (Event)
    meeting = dataset.make("Event")
    meeting.id = dataset.make_id("meeting", record_id)
    meeting.add("recordId", record_id)

    meeting_name = f"Meeting: {rep_name}"
    if orgs:
        meeting_name = f"{meeting_name} with {orgs[0].first('name')}"
        if len(orgs) > 1:
            meeting_name = f"{meeting_name} and others"
    meeting.add("name", meeting_name)

    meeting.add("summary", row.get("purpose"))
    meeting.add("date", parse_date(row.get("date"), "%d/%m/%Y"))

    meeting.add("organizer", rep)
    for org in orgs:
        meeting.add("involved", org)
    if dept:
        meeting.add("organizer", dept)

    meeting.add("notes", row.get("others_at_the_meeting"))

    meeting.add("keywords", "Meeting")

    source_url = (row.get("source") or "").strip()
    if source_url.startswith(BASE_MEETING_URL) and source_url.endswith(".0"):
        source_url = source_url[:-2]
    if not source_url:
        source_url = f"{BASE_MEETING_URL}{record_id}"
    meeting.add("sourceUrl", source_url)

    dataset.emit(meeting)


def crawl(dataset: Dataset):
    # Fetch the CSV resource using the URL from config
    url = "https://openaccess.transparency.org.uk/data/iw_uk.csv"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
    }

    # We use verify=False because the server's SSL certificate chain is
    # currently failing verification in this environment.
    path = dataset.fetch_resource("iw_uk.csv", url, headers=headers, verify=False)

    with open(path, "r", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            # # Filter for meetings from 2024 onwards
            # date_str = row.get("date")
            # if date_str:
            #     try:
            #         dt = datetime.strptime(date_str, "%d/%m/%Y")
            #         if dt < datetime(2025, 1, 1):
            #             continue
            #     except ValueError:
            #         pass
            crawl_row(dataset, row)
