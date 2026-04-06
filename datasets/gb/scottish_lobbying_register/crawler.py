import requests
import time
from bs4 import BeautifulSoup

BASE_URL = "https://www.lobbying.scot/SPS/"
COOKIE_URL = f"{BASE_URL}/?AspxAutoDetectCookieSupport=1"
SEARCH_URL = f"{BASE_URL}/Search/Search?AspxAutoDetectCookieSupport=1"
RESULT_URL = f"{BASE_URL}/Search/SearchResult"

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
        timeout=60)
    response.raise_for_status()

    # extract registrants from the page
    registrants_soup = BeautifulSoup(response.text, "html.parser")
    registrants_table = registrants_soup.select_one("table")

    # loop through rows
    for row in registrants_table.select("tr")[1:]:
        # extract org ID
        org_id = row.select_one("td a").get("href").split("?")[0].split("/")[-1]

        # create registrant
        # lobbying_role = row.select_one('[data-title="Lobbying Role"] span').text.strip()
        registrant_type = row.select_one('[data-title="Registrant Type"] span').text.strip()

        registrant_schema = 'LegalEntity'
        if registrant_type in ('Company', 'Limited Liability Partnership'):
            registrant_schema = 'Company'
        elif registrant_type in ('Charity, Trust or Advocacy Body', 'Charity / Trust / Advocacy Body', 'Union', 'Housing Association', 'Society', 'Representative Body'):
            registrant_schema = 'Organization'
        elif registrant_type == 'Sole trader or paid individual':
            registrant_schema = 'Person'
        elif registrant_type in ('Independent Statutory Body'):
            registrant_schema = 'PublicBody'

        dataset.log.info(f"Processing registrant {org_id}")
        registrant = dataset.make(registrant_schema)
        registrant.id = dataset.make_id('scottish_lobbying_register', org_id)


        # get business name (if it exists)
        lobbyist_name = row.select_one('[data-title="Name of Lobbyist"] span').text.strip()
        registrant.add("name", lobbyist_name)

        business_name = row.select_one('[data-title="Business Name"] span').text.strip()
        if business_name:
            registrant.add("alias", business_name)
        company_name = row.select_one('[data-title="Company Name"] span').text.strip()
        if company_name:
            registrant.add("alias", company_name)
        
        subject_area = row.select_one('[data-title="Registrant Subject Area"] span').text.strip()
        registrant.add("sector", subject_area)

        # more data exists on the details page, we'll get that as well
        # TODO: Do we need to refresh the token after a timeout?
        details_page = dataset.fetch_text(f"{BASE_URL}/Manage/RegisteredUserSearchDetail/{org_id}", cache_days=30, sleep=0.1)
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
        
        responsible_person_entry = details_soup.select_one('input[name="ResponsiblePerson"]').get("value")
        if responsible_person_entry:
            responsible_person = dataset.make("Person")
            responsible_person.id = dataset.make_id('scottish_lobbying_register', org_id, responsible_person_entry)
            responsible_person.add("name", responsible_person_entry)
            dataset.emit(responsible_person)

            responsible_person_employment = dataset.make("Employment")
            responsible_person_employment.id = dataset.make_id('scottish_lobbying_register', org_id, responsible_person_entry, "employment")
            responsible_person_employment.add("employer", registrant)
            responsible_person_employment.add("employee", responsible_person)
            dataset.emit(responsible_person_employment)
        
        dataset.emit(registrant)

        # now let's get the individual meetings
        # https://www.lobbying.scot/SPS/Search/SearchResult?id=a1c36112-6b57-47ff-9228-86b086ac2996
        # returns_page = dataset.fetch_html(f"{BASE_URL}/Search/SearchResult?id={org_id}", cache_days=30)


