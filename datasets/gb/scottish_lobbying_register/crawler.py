import requests
from bs4 import BeautifulSoup
import csv

from muckrake.util import parse_date

BASE_URL = "https://www.lobbying.scot/SPS/"
COOKIE_URL = f"{BASE_URL}/?AspxAutoDetectCookieSupport=1"
SEARCH_URL = f"{BASE_URL}/Search/Search?AspxAutoDetectCookieSupport=1"
RESULT_URL = f"{BASE_URL}/Search/SearchResult"

INFORMATION_RETURNS_COLUMNS = [
    "Count",
    "Return ID",
    "Date of lobbying activity",
    "Published date",
    "Registrant name",
    "Registrant subject area",
    "Person lobbied roles",
    "Persons lobbied",
    "Location",
    "Lobbying activity",
    "Communication type",
    "Lobbyist names",
    "Undertaken on registrants behalf",
    "Client name",
    "Purpose of lobbying",
    "Registrant type",
]


def parse_imported_date(value):
    if not value:
        return None
    parsed = parse_date(value, "%d/%m/%Y %H:%M:%S")
    if parsed is None:
        raise ValueError(f"Could not parse imported date: {value}")
    return parsed


def crawl(dataset):
    # create session
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    session.get(BASE_URL, timeout=60, allow_redirects=False)
    session.get(COOKIE_URL, timeout=60)

    headers = {key: str(value) for key, value in session.headers.items()}

    # get verification token
    response = session.get(SEARCH_URL, timeout=60)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.select_one('input[name="__RequestVerificationToken"]')
    if token_input is None:
        raise ValueError("Missing request verification token on search page")

    token = token_input.get("value")

    # Fetch the page with all the registrants (1746 results)
    response = session.post(
        RESULT_URL,
        data={
            "__RequestVerificationToken": token,
            "InformationReturnHistory.TypeOfSearch": "Registrants",
            "InformationReturnHistory.RegistrantSearchSortBy": "Alphabetical",
        },
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    # extract registrants from the page
    registrants_soup = BeautifulSoup(response.text, "html.parser")
    registrants_table = registrants_soup.select_one("table")
    if registrants_table is None:
        raise ValueError("Missing registrants table")

    # loop through rows
    for row in registrants_table.select("tr")[1:]:
        # extract org ID
        org_link = row.select_one("td a")
        if org_link is None:
            raise ValueError("Missing registrant link")
        href = org_link.get("href")
        if not isinstance(href, str) or not href:
            raise ValueError("Missing registrant link href")
        org_id = href.split("?")[0].split("/")[-1]
        if not org_id:
            raise ValueError("Missing registrant ID")

        # create registrant
        # lobbying_role = row.select_one('[data-title="Lobbying Role"] span').text.strip()
        registrant_type_tag = row.select_one('[data-title="Registrant Type"] span')
        if registrant_type_tag is None:
            raise ValueError("Missing registrant type")
        registrant_type = registrant_type_tag.text.strip()

        # TODO: add topics for unions and so on
        registrant_schema = "LegalEntity"
        if registrant_type in ("Company", "Limited Liability Partnership"):
            registrant_schema = "Company"
        elif registrant_type in (
            "Charity, Trust or Advocacy Body",
            "Charity / Trust / Advocacy Body",
            "Union",
            "Housing Association",
            "Society",
            "Representative Body",
        ):
            registrant_schema = "Organization"
        elif registrant_type == "Sole trader or paid individual":
            registrant_schema = "Person"
        elif registrant_type in ("Independent Statutory Body"):
            registrant_schema = "PublicBody"

        dataset.log.info(f"Processing registrant {org_id}")
        registrant = dataset.make(registrant_schema)
        registrant.id = dataset.make_id("scottish_lobbying_register", org_id)

        # get business name (if it exists)
        lobbyist_name_tag = row.select_one('[data-title="Name of Lobbyist"] span')
        if lobbyist_name_tag is None:
            raise ValueError(f"Missing lobbyist name for registrant {org_id}")
        lobbyist_name = lobbyist_name_tag.text.strip()
        registrant.add("name", lobbyist_name)

        business_name_tag = row.select_one('[data-title="Business Name"] span')
        business_name = business_name_tag.text.strip() if business_name_tag else ""
        if business_name:
            registrant.add("alias", business_name)
        company_name_tag = row.select_one('[data-title="Company Name"] span')
        company_name = company_name_tag.text.strip() if company_name_tag else ""
        if company_name:
            registrant.add("alias", company_name)

        subject_area_tag = row.select_one('[data-title="Registrant Subject Area"] span')
        subject_area = subject_area_tag.text.strip() if subject_area_tag else ""
        if subject_area:
            registrant.add("sector", subject_area)

        # more data exists on the details page, we'll get that as well
        # TODO: Do we need to refresh the token after a timeout?
        details_page = dataset.fetch_text(
            f"{BASE_URL}/Manage/RegisteredUserSearchDetail/{org_id}",
            cache_days=30,
            sleep=0.1,
        )
        if details_page is None:
            raise ValueError(f"Missing details page for registrant {org_id}")
        details_soup = BeautifulSoup(details_page, "html.parser")

        address_lines = []
        n = 1
        while True:
            field = details_soup.select_one(f'input[name="Line{n}"]')
            if field is None:
                break
            address_lines.append(field.get("value"))
            n += 1
        postcode = details_soup.select_one('input[name="PostCode"]')
        postcode_value = postcode.get("value") if postcode else None
        all_parts = address_lines + ([postcode_value] if postcode_value else [])
        if any(all_parts):
            address = "\n".join(filter(None, all_parts))
            registrant.add("address", address)

        responsible_person = details_soup.select_one('input[name="ResponsiblePerson"]')
        responsible_person_entry = (
            responsible_person.get("value") if responsible_person else None
        )
        if responsible_person_entry:
            responsible_person = dataset.make("Person")
            responsible_person.id = dataset.make_id(
                "scottish_lobbying_register", org_id, responsible_person_entry
            )
            responsible_person.add("name", responsible_person_entry)
            dataset.emit(responsible_person)

            responsible_person_employment = dataset.make("Employment")
            responsible_person_employment.id = dataset.make_id(
                "scottish_lobbying_register",
                org_id,
                responsible_person_entry,
                "employment",
            )
            responsible_person_employment.add("employer", registrant)
            responsible_person_employment.add("employee", responsible_person)
            dataset.emit(responsible_person_employment)

        dataset.emit(registrant)

    # now let's get the individual meetings
    # https://www.lobbying.scot/SPS/Search/SearchResult?id=a1c36112-6b57-47ff-9228-86b086ac2996
    # returns_page = dataset.fetch_html(f"{BASE_URL}/Search/SearchResult?id={org_id}", cache_days=30)
    # use the CSVs, maybe download the unfiltered one and do it all in one go?

    information_returns_payload = {
        "__RequestVerificationToken": token,
        "InformationReturnHistory.TypeOfSearch": "InformationReturns",
        # "InformationReturnHistory.SearchByStartDate": "",
        # "InformationReturnHistory.SearchByEndDate": "",
        # "InformationReturnHistory.AllText": "",
        # "InformationReturnHistory.FullName": "",
        # "InformationReturnHistory.SubstantiveOrNil": "",
        # "InformationReturnHistory.SearchByRoleID": "0",
        # "InformationReturnHistory.SearchByLobbiedPersonID": "0",
        # "InformationReturnHistory.CommunicationTypeID": "0",
        # "InformationReturnHistory.RegistrantSearchSortBy": "Alphabetical",
        # "InformationReturnHistory.ActiveRegistrants": "false",
        # "InformationReturnHistory.InactiveRegistrants": "false",
        # "InformationReturnHistory.VoluntaryRegistrants": "false",
        # "InformationReturnHistory.FullNameRegistrant": "",
        # "InformationReturnHistory.AdminLobbyingRoleId_Registrant": "0",
        # "InformationReturnHistory.RegistrantSubjectAreaId_Registrant": "0",
        # "urlGetLobbiedPerson": "/SPS/LobbyingRegister/GetLobbiedPersonByRole",
        # "urlGetSubmissionPeriods": "/SPS/LobbyingRegister/GetSubmissionPeriods",
    }

    response = session.post(
        "https://www.lobbying.scot/SPS/Search/SearchResult",
        data=information_returns_payload,
        headers=headers,
        timeout=300,
    )
    response.raise_for_status()

    results_soup = BeautifulSoup(response.text, "html.parser")
    export_form = results_soup.select_one("form#OutputSearchResult")
    if export_form is None:
        raise ValueError("Missing export form on information returns results page")

    export_token_input = export_form.select_one(
        'input[name="__RequestVerificationToken"]'
    )
    if export_token_input is None:
        raise ValueError("Missing export token on information returns results page")

    export_payload = {
        "__RequestVerificationToken": export_token_input.get("value"),
        "QuerystringSearch": "False",
        "InformationReturnHistory.UserId": "",
        "InformationReturnHistory.Hash": "",
        "InformationReturnHistory.SearchAll": "False",
        "Command": "downloadCSV",
    }

    csv_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://lobbying.scot",
        "DNT": "1",
        "Sec-GPC": "1",
        "Referer": "https://lobbying.scot/SPS/Search/SearchResult",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
    }

    dataset.log.info("Fetching information returns CSV")

    path = dataset.fetch_resource(
        "information_returns.csv",
        "https://www.lobbying.scot/SPS/Search/OutputSearchResult",
        session=session,
        method="POST",
        headers=csv_headers,
        data=export_payload,
        timeout=300,
    )

    with open(path, "r", encoding="utf-8", newline="") as f:
        dataset.log.info("Processing information returns")
        reader = csv.DictReader(f, fieldnames=INFORMATION_RETURNS_COLUMNS)
        next(reader, None)

        # Skip nil returns so only actual lobbying activity is emitted.
        rows = [
            row
            for row in reader
            if row.get("Date of lobbying activity")
            and row.get("Date of lobbying activity") != "Nil Return"
        ]

        for row in rows:
            record_id = row.get("Return ID")
            dataset.log.info(f"Processing information return {record_id}")

            meeting = dataset.make("Event")
            meeting.id = dataset.make_id(
                "scottish_lobbying_register", "information_return", record_id
            )
            meeting.add("recordId", record_id)

            lobbying_activity = row.get("Lobbying activity")
            meeting.add("name", lobbying_activity)

            purpose_of_lobbying = row.get("Purpose of lobbying")
            meeting.add("summary", purpose_of_lobbying)
            communication_type = row.get("Communication type")
            meeting.add("description", f"Communication Type: {communication_type}")

            date_of_lobbying_activity = row.get("Date of lobbying activity")
            published_date = row.get("Published date")
            if date_of_lobbying_activity:
                meeting.add("date", parse_imported_date(date_of_lobbying_activity))
            elif published_date:
                meeting.add("date", parse_imported_date(published_date))

            location = row.get("Location")
            if location:
                meeting.add("location", location)

            # create hosts (politicians)
            persons_lobbied = row.get("Persons lobbied")
            persons_lobbied = (
                [p.strip() for p in persons_lobbied.split(";")]
                if persons_lobbied
                else []
            )

            persons_lobbied_roles = row.get("Person lobbied roles")
            persons_lobbied_roles = (
                [r.strip() for r in persons_lobbied_roles.split(";")]
                if persons_lobbied_roles
                else []
            )

            for i, name in enumerate(persons_lobbied):
                politician = dataset.make("Person")
                politician.id = dataset.make_id(
                    "scottish_lobbying_register", "politician", name
                )
                politician.add("name", name)
                politician.add("jurisdiction", "gb-sct")
                politician.add("topics", "role.pep")
                # TODO: add Scottish Parliament / Government as employer
                dataset.emit(politician)
                meeting.add("organizer", politician)

            # create meeting participants
            registrant_name = row.get("Registrant name")
            undertaken_on_registrants_behalf = row.get(
                "Undertaken on registrants behalf"
            )
            if undertaken_on_registrants_behalf == "No":
                # create lobbyist
                lobbyist = dataset.make("Organization")
                lobbyist.id = dataset.make_id(
                    "scottish_lobbying_register", "lobbyist", registrant_name
                )
                lobbyist.add("name", registrant_name)
                lobbyist.add("topics", "role.lobby")
                dataset.emit(lobbyist)
                meeting.add("involved", lobbyist)

                # create client
                client = dataset.make("Organization")
                client_name = row.get("Client name")
                client.id = dataset.make_id(
                    "scottish_lobbying_register", "client", client_name
                )
                client.add("name", client_name)
                dataset.emit(client)
                meeting.add("involved", client)

                # link lobbyist to client
                lobbying_relationship = dataset.make("Representation")
                lobbying_relationship.id = dataset.make_id(
                    "scottish_lobbying_register", lobbyist.id, client.id
                )
                lobbying_relationship.add("agent", lobbyist)
                lobbying_relationship.add("client", client)
                # TODO: add date
                dataset.emit(lobbying_relationship)

                # add lobbyist employment
                employees = row.get("Lobbyist names")
                employees = (
                    [e.strip() for e in employees.split(";")] if employees else []
                )
                for employee_name in employees:
                    employee = dataset.make("Person")
                    employee.id = dataset.make_id(
                        "scottish_lobbying_register", "employee", employee_name
                    )
                    employee.add("name", employee_name)
                    dataset.emit(employee)
                    meeting.add("involved", employee)

                    employment = dataset.make("Employment")
                    employment.id = dataset.make_id(
                        "scottish_lobbying_register",
                        "employment",
                        lobbyist.id,
                        employee_name,
                    )
                    employment.add("employer", lobbyist)
                    employment.add("employee", employee)
                    dataset.emit(employment)

            dataset.emit(meeting)
