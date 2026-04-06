import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from muckrake.dataset import Dataset
from muckrake.extract.fetch import fetch_text
from muckrake.util import parse_date


BASE_URL = "https://www.lobbying.scot"
HOME_URL = f"{BASE_URL}/SPS/"
COOKIE_URL = f"{BASE_URL}/SPS/?AspxAutoDetectCookieSupport=1"
SEARCH_URL = f"{BASE_URL}/SPS/Search/Search?AspxAutoDetectCookieSupport=1"
RESULT_URL = f"{BASE_URL}/SPS/Search/SearchResult"
MAX_REGISTRANTS = 10
URL_RE = re.compile(r"https?://\S+")


def attr_text(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # The site expects this cookie bootstrap before the search form works.
    session.get(HOME_URL, timeout=60, allow_redirects=False)
    session.get(COOKIE_URL, timeout=60)
    return session


def get_request_verification_token(session: requests.Session) -> str:
    response = session.get(SEARCH_URL, timeout=60)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.select_one('input[name="__RequestVerificationToken"]')
    if token_input is None:
        raise ValueError("Missing request verification token on search page")

    token = attr_text(token_input.get("value"))
    if not token:
        raise ValueError("Empty request verification token on search page")
    return token


def fetch_registrants_page(session: requests.Session, token: str) -> str:
    payload = {
        "__RequestVerificationToken": token,
        "InformationReturnHistory.TypeOfSearch": "Registrants",
        "InformationReturnHistory.SearchByStartDate": "",
        "InformationReturnHistory.SearchByEndDate": "",
        "InformationReturnHistory.AllText": "",
        "InformationReturnHistory.FullName": "",
        "InformationReturnHistory.SubstantiveOrNil": "",
        "InformationReturnHistory.SearchByRoleID": "0",
        "InformationReturnHistory.SearchByLobbiedPersonID": "0",
        "InformationReturnHistory.CommunicationTypeID": "0",
        "InformationReturnHistory.RegistrantSearchSortBy": "Alphabetical",
        "InformationReturnHistory.ActiveRegistrants": "false",
        "InformationReturnHistory.InactiveRegistrants": "false",
        "InformationReturnHistory.VoluntaryRegistrants": "false",
        "InformationReturnHistory.FullNameRegistrant": "",
        "InformationReturnHistory.AdminLobbyingRoleId_Registrant": "0",
        "InformationReturnHistory.RegistrantSubjectAreaId_Registrant": "0",
        "urlGetLobbiedPerson": "/SPS/LobbyingRegister/GetLobbiedPersonByRole",
        "urlGetSubmissionPeriods": "/SPS/LobbyingRegister/GetSubmissionPeriods",
    }
    headers = {"Origin": BASE_URL, "Referer": SEARCH_URL}

    response = session.post(RESULT_URL, data=payload, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


def extract_registrants(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    registrants = []

    for row in soup.select("tr"):
        detail_link = row.select_one('a[href*="RegisteredUserSearchDetail"]')
        returns_link = row.select_one('a[href*="SearchResult?id="]')
        if detail_link is None or returns_link is None:
            continue

        data = {}
        for cell in row.select("td[data-title]"):
            data[cell.get("data-title", "")] = cell.get_text(" ", strip=True)

        detail_href = attr_text(detail_link.get("href"))
        returns_href = attr_text(returns_link.get("href"))
        detail_url = urljoin(BASE_URL, detail_href or "")
        if not detail_url:
            continue
        returns_url = urljoin(BASE_URL, returns_href or "")
        if not returns_url:
            continue

        registrants.append(
            {
                "name": data.get("Name of Lobbyist", ""),
                "detail_url": detail_url,
                "returns_url": returns_url,
                "registration_date": data.get("True Registration Date", ""),
                "status": data.get("Status", ""),
                "business_name": data.get("Business Name", ""),
                "company_name": data.get("Company Name", ""),
                "lobbying_role": data.get("Lobbying Role", ""),
                "registrant_type": data.get("Registrant Type", ""),
                "subject_area": data.get("Registrant Subject Area", ""),
            }
        )

    return registrants


def get_input_value(soup: BeautifulSoup, name: str) -> str | None:
    field = soup.select_one(f'input[name="{name}"]')
    if field is None:
        return None
    value = attr_text(field.get("value"))
    return value or None


def get_textarea_value(soup: BeautifulSoup, name: str) -> str | None:
    field = soup.select_one(f'textarea[name="{name}"]')
    if field is None:
        return None
    value = field.get_text(" ", strip=True)
    return value or None


def get_selected_text(soup: BeautifulSoup, name: str) -> str | None:
    field = soup.select_one(f'select[name="{name}"] option[selected]')
    if field is None:
        return None
    value = field.get_text(" ", strip=True)
    return value or None


def get_radio_value(soup: BeautifulSoup, name: str) -> str | None:
    field = soup.select_one(f'input[name="{name}"][checked]')
    if field is None:
        return None
    value = attr_text(field.get("value"))
    return value or None


def extract_code_of_conduct_details(soup: BeautifulSoup) -> str | None:
    label = None
    for candidate in soup.find_all("label"):
        if re.search(
            r"Code of conduct details", candidate.get_text(" ", strip=True), re.I
        ):
            label = candidate
            break
    if label is None:
        return None

    container = label.find_next("div", class_="code-conduct-details")
    if container is None:
        return None

    value = container.get_text(" ", strip=True)
    return value or None


def extract_detail_data(html: str) -> dict[str, str | list[str] | None]:
    soup = BeautifulSoup(html, "html.parser")
    line1 = get_input_value(soup, "Line1")
    line2 = get_input_value(soup, "Line2")
    postcode = get_input_value(soup, "PostCode")

    address_parts = [part for part in (line1, line2, postcode) if part]
    code_of_conduct_details = extract_code_of_conduct_details(soup)

    return {
        "full_name": get_input_value(soup, "FullName"),
        "business_name": get_input_value(soup, "BusinessName"),
        "address": ", ".join(address_parts) or None,
        "responsible_person": get_input_value(soup, "ResponsiblePerson"),
        "other_information": get_textarea_value(soup, "OtherInformation"),
        "is_code_of_conduct": get_radio_value(soup, "IsCodeOfConduct"),
        "code_of_conduct_details": code_of_conduct_details,
        "websites": URL_RE.findall(code_of_conduct_details or ""),
    }


def extract_returns(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    model = soup.select_one("#ModelJSONInformationReturnSearchResult")
    if model is None:
        raise ValueError("Missing return search JSON model")

    raw_value = attr_text(model.get("value"))
    if raw_value is None:
        raise ValueError("Empty return search JSON model")
    payload = json.loads(unescape(raw_value))
    return payload.get("InformationReturnSearchResult", [])


def extract_return_detail_data(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    address_parts = [
        get_input_value(soup, "InformationReturn.AddressLineOne"),
        get_input_value(soup, "InformationReturn.AddressLineTwo"),
        get_input_value(soup, "InformationReturn.AddressLineThree"),
        get_input_value(soup, "InformationReturn.AddressLineFour"),
        get_input_value(soup, "InformationReturn.PostCode"),
    ]

    return {
        "registrant_name": get_input_value(soup, "RegistrantName"),
        "date": get_input_value(soup, "Date"),
        "time": get_input_value(soup, "Time"),
        "submission_period": get_selected_text(
            soup, "InformationReturn.SubmissionPeriod"
        ),
        "communication_type": get_selected_text(
            soup, "InformationReturn.CommunicationType"
        ),
        "meeting_description": get_textarea_value(
            soup, "InformationReturn.MeetingDescription"
        ),
        "purpose": get_textarea_value(soup, "InformationReturn.PurposeOfLobbying"),
        "individual": get_input_value(
            soup, "InformationReturn.IndividualCarriedCommunication[0].IndividualName"
        ),
        "represented_name": get_input_value(soup, "InformationReturn.PersonName"),
        "own_behalf": get_radio_value(soup, "InformationReturn.RegistrantOwnBehalf"),
        "location": ", ".join(part for part in address_parts if part) or None,
        "publish_date": get_input_value(soup, "InformationReturn.PublishDate"),
    }


def split_semicolon_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def normalize_person_name(name: str) -> str:
    if "," not in name:
        return name.strip()
    last, first = [part.strip() for part in name.split(",", 1)]
    if not first:
        return last
    return f"{first} {last}"


def make_person(dataset: Dataset, name: str, topic: str | None = None):
    person = dataset.make("Person")
    person.id = dataset.make_id("person", name)
    person.add("name", name)
    person.add("jurisdiction", "gb")
    if topic:
        person.add("topics", topic)
    return person


def make_client_organization(dataset: Dataset, name: str):
    org = dataset.make("Organization")
    org.id = dataset.make_id("represented_org", name)
    org.add("name", name)
    org.add("jurisdiction", "gb")
    org.add("country", "gb")
    return org


def make_meeting_name(registrant_name: str, lobbied_people: list[str]) -> str:
    if not lobbied_people:
        return f"Meeting involving {registrant_name}"
    if len(lobbied_people) == 1:
        return f"Meeting: {registrant_name} with {lobbied_people[0]}"
    return f"Meeting: {registrant_name} with {lobbied_people[0]} and others"


def build_meeting_notes(
    return_row: dict, return_detail: dict[str, str | None]
) -> str | None:
    lines = []

    if return_detail.get("time") and return_detail["time"] != "00:00":
        lines.append(f"Time: {return_detail['time']}")
    if return_detail.get("communication_type"):
        lines.append(f"Communication type: {return_detail['communication_type']}")
    if return_detail.get("submission_period"):
        lines.append(f"Submission period: {return_detail['submission_period']}")
    if return_detail.get("own_behalf") == "Yes":
        lines.append("Registrant acted on its own behalf")
    elif return_detail.get("own_behalf") == "No":
        lines.append("Registrant acted on behalf of another organization")
    if return_row.get("LobbiedPersonRoleDescription"):
        lines.append(
            f"Lobbied person roles: {return_row['LobbiedPersonRoleDescription']}"
        )
    if return_row.get("LobbiedPersonPoliticalPartyDescription"):
        lines.append(
            f"Political parties: {return_row['LobbiedPersonPoliticalPartyDescription']}"
        )
    if return_detail.get("publish_date"):
        lines.append(f"Published: {return_detail['publish_date']}")

    if not lines:
        return None
    return "\n".join(lines)


def emit_meeting(
    dataset: Dataset,
    registrant,
    registrant_name: str,
    return_row: dict,
    return_detail: dict[str, str | None],
    people: dict[str, Any],
    clients: dict[str, Any],
):
    lobbied_people = [
        normalize_person_name(name)
        for name in split_semicolon_values(return_row.get("LobbiedPerson"))
    ]
    representative_names = [
        normalize_person_name(name)
        for name in split_semicolon_values(
            return_detail.get("individual")
            or return_row.get("IndividualCarriedCommunication")
        )
    ]

    meeting = dataset.make("Event")
    meeting.id = dataset.make_id("meeting", return_row["InformationReturnID"])
    meeting.add("recordId", str(return_row["InformationReturnID"]))
    meeting.add(
        "name",
        make_meeting_name(
            return_detail.get("registrant_name") or registrant_name,
            lobbied_people,
        ),
    )
    meeting_date = parse_date(
        return_detail.get("date") or return_row.get("InformationReturnDateString")
    )
    if meeting_date:
        meeting.add("date", meeting_date)
    meeting.add("country", "gb")
    meeting.add("keywords", "Meeting")
    meeting.add(
        "sourceUrl",
        f"{BASE_URL}/SPS/InformationReturn/SearchInformationReturnDetail/{return_row['InformationReturnID']}",
    )
    meeting.add("publisher", "Scottish Parliament")
    meeting.add("publisherUrl", HOME_URL)
    meeting.add("organizer", registrant)
    meeting.add("involved", registrant)

    if return_detail.get("purpose"):
        meeting.add("summary", return_detail["purpose"])
    if return_detail.get("meeting_description"):
        meeting.add("description", return_detail["meeting_description"])
    if return_detail.get("location"):
        meeting.add("location", return_detail["location"])

    for name in lobbied_people:
        person = people.get(name)
        if person is None:
            person = make_person(dataset, name, topic="role.pep")
            dataset.emit(person)
            people[name] = person
        meeting.add("involved", person)

    for name in representative_names:
        person = people.get(name)
        if person is None:
            person = make_person(dataset, name)
            dataset.emit(person)
            people[name] = person
        meeting.add("involved", person)

    represented_name = return_detail.get("represented_name") or return_row.get(
        "PersonName"
    )
    if represented_name:
        client_name = represented_name.strip()
        client = clients.get(client_name)
        if client is None:
            client = make_client_organization(dataset, client_name)
            dataset.emit(client)
            clients[client_name] = client
        meeting.add("involved", client)

    notes = build_meeting_notes(return_row, return_detail)
    if notes:
        meeting.add("notes", notes)

    dataset.emit(meeting)


def build_notes(
    item: dict[str, str], details: dict[str, str | list[str] | None]
) -> str | None:
    lines = []

    if item.get("registration_date"):
        lines.append(
            f"Scottish Lobbying Register registration date: {item['registration_date']}"
        )
    if details.get("responsible_person"):
        lines.append(f"Responsible person: {details['responsible_person']}")
    if details.get("is_code_of_conduct") == "True":
        lines.append("Code of conduct: Yes")
    elif details.get("is_code_of_conduct") == "False":
        lines.append("Code of conduct: No")
    if details.get("code_of_conduct_details"):
        lines.append(f"Code of conduct details: {details['code_of_conduct_details']}")
    if details.get("other_information"):
        lines.append(str(details["other_information"]))

    if not lines:
        return None
    return "\n".join(lines)


def make_organization(
    dataset: Dataset,
    item: dict[str, str],
    details: dict[str, str | list[str] | None],
):
    registrant_id = urlparse(item["detail_url"]).path.rstrip("/").split("/")[-1]
    name = details.get("full_name") or item["name"]
    if not name:
        raise ValueError(f"Missing registrant name for {item['detail_url']}")

    org = dataset.make("Organization")
    org.id = dataset.make_id("organization", registrant_id)
    org.add("name", name)
    org.add("jurisdiction", "gb")
    org.add("country", "gb")
    org.add("topics", "role.lobby")
    org.add("sourceUrl", item["detail_url"])
    org.add("publisher", "Scottish Parliament")
    org.add("publisherUrl", HOME_URL)

    for alias in (
        item.get("name"),
        item.get("business_name"),
        item.get("company_name"),
        details.get("business_name"),
    ):
        if alias and alias != name:
            org.add("alias", alias)

    if item.get("registrant_type"):
        org.add("legalForm", item["registrant_type"])
    if item.get("lobbying_role"):
        org.add("classification", item["lobbying_role"])
    if item.get("subject_area"):
        org.add("sector", item["subject_area"])
    if item.get("status"):
        org.add("status", item["status"])
    if details.get("address"):
        org.add("address", details["address"])

    websites = details.get("websites")
    if isinstance(websites, list):
        for website in websites:
            org.add("website", website)

    notes = build_notes(item, details)
    if notes:
        org.add("notes", notes)

    return org


def crawl(dataset: Dataset):
    people: dict[str, Any] = {}
    clients: dict[str, Any] = {}

    session = make_session()
    headers = {key: str(value) for key, value in session.headers.items()}
    token = get_request_verification_token(session)
    html = fetch_registrants_page(session, token)
    all_registrants = extract_registrants(html)
    registrants = all_registrants[:MAX_REGISTRANTS]

    dataset.log.info(
        "Found %s registrants, processing first %s",
        len(all_registrants),
        len(registrants),
    )

    for item in registrants:
        dataset.log.info("Fetching registrant details for %s", item["name"])
        detail_html = fetch_text(
            item["detail_url"],
            headers=headers,
            cache=dataset.cache,
            cache_days=30,
        )
        if not detail_html:
            raise ValueError(f"Missing registrant detail page: {item['detail_url']}")
        details = extract_detail_data(detail_html)
        org = make_organization(dataset, item, details)
        dataset.emit(org)

        dataset.log.info("Fetching returns for %s", item["name"])
        returns_html = fetch_text(
            item["returns_url"],
            headers=headers,
            cache=dataset.cache,
            cache_days=30,
        )
        if not returns_html:
            raise ValueError(f"Missing returns page: {item['returns_url']}")
        for return_row in extract_returns(returns_html):
            if return_row.get("InformationReturnDateString") == "Nil Return":
                continue

            return_id = return_row.get("InformationReturnID")
            if not return_id:
                continue

            return_detail_url = f"{BASE_URL}/SPS/InformationReturn/SearchInformationReturnDetail/{return_id}"
            return_detail_html = fetch_text(
                return_detail_url,
                headers=headers,
                cache=dataset.cache,
                cache_days=30,
            )
            if not return_detail_html:
                raise ValueError(f"Missing return detail page: {return_detail_url}")
            return_detail = extract_return_detail_data(return_detail_html)
            emit_meeting(
                dataset,
                org,
                item["name"],
                return_row,
                return_detail,
                people,
                clients,
            )
