import requests
from bs4 import BeautifulSoup
import datetime
from urllib.parse import urljoin

from muckrake.utils import normalize_gb_coh

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0',
    'Sec-GPC': '1'
}

BASE_URL = 'https://foreign-influence-registration-scheme.service.gov.uk/public-register'


def get_summary_block(soup, title: str):
    """Get a summary block by its title."""
    title_element = soup.find('h2', class_='gi-summary-block__title', string=title)  # type: ignore
    if not title_element:
        return None
    
    block = title_element.find_parent('div', class_='gi-summary-block')
    return block


def extract_field_value(block, key_text: str) -> list[str] | None:
    """Extract a field value from a summary block given the key text. Returns a list of values or None."""
    key_element = block.find('dt', class_='gi-summary-blocklist__key', string=key_text)  # type: ignore
    if not key_element:
        return None

    value_element = key_element.find_next_sibling('dd', class_='gi-summary-blocklist__value')
    if not value_element:
        return None

    paragraphs = value_element.find_all('p')
    if not paragraphs:
        return None

    texts = [p.get_text(strip=True) for p in paragraphs]
    return texts


def parse_date(text: str) -> str | None:
    """Parse dates like '04 May 2025' to ISO format 'YYYY-MM-DD'.
    Returns None if parsing fails. If a range is provided, takes the first date.
    """
    if not text:
        return None

    # If the field contains a range like '04 May 2025 to 10 May 2025', take first part
    for sep in (" to ", "–", "—", "-"):
        if sep in text:
            text = text.split(sep)[0].strip()
            break

    # Try full month name then abbreviated month name
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            dt = datetime.datetime.strptime(text.strip(), fmt).date()
            return dt.isoformat()
        except ValueError:
            continue

    return None





def crawl(dataset):
    response = requests.get(BASE_URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, 'html.parser')

    for link in soup.select('a.card__link'):
        href = link.get('href')
        if not href or isinstance(href, list):
            continue

        article_url = urljoin(BASE_URL, href)
        
        article_response = requests.get(article_url, headers=HEADERS)
        article_soup = BeautifulSoup(article_response.text, 'html.parser')



        # Create lobbyist entity
        registrant_block = get_summary_block(article_soup, 'Registrant')
        if not registrant_block:
            continue
        
        lobbyist = dataset.make("Company")

        registrant_name = extract_field_value(registrant_block, 'Name')
        registrant_company_number = extract_field_value(registrant_block, 'Company registration number')
        lobbyist.id = dataset.make_id('lobbyist', registrant_name, reg_nr=registrant_company_number, register="GB-COH")

        if registrant_company_number:
            lobbyist.add('registrationNumber', f"GB-COH-{normalize_gb_coh(registrant_company_number[0])}")
        
        lobbyist.add('topics', 'role.lobby')
        lobbyist.add('name', registrant_name)

        registrant_name_previous = extract_field_value(registrant_block, 'Previous names')
        if registrant_name_previous:
            lobbyist.add('previousName', registrant_name_previous)

        registrant_country = extract_field_value(registrant_block, 'Country or territory of incorporation or main office')
        if registrant_country:
            lobbyist.add('country', registrant_country)
        
        registrant_address = extract_field_value(registrant_block, 'Registered or main address')
        if registrant_address:
            registrant_address = "\n".join(registrant_address)
            lobbyist.add('address', registrant_address)

        dataset.emit(lobbyist)



        # Create client entity
        arrangement_block = get_summary_block(article_soup, 'Arrangement')
        if not arrangement_block:
            continue

        client = dataset.make("PublicBody")
        

        arrangement_name = extract_field_value(arrangement_block, 'Name of foreign power')
        client.id = dataset.make_id('client', arrangement_name)
        client.add('name', arrangement_name)
        client.add('topics', 'gov')

        arrangement_country = extract_field_value(arrangement_block, 'Country or territory of foreign power')
        if arrangement_country:
            client.add('country', arrangement_country)
        
        dataset.emit(client)




        # Create representation linking lobbyist -> client
        activity_block = get_summary_block(article_soup, 'Activity overview')
        if not activity_block:
            continue

        representation = dataset.make("Representation")
        representation.id = dataset.make_id('rep', lobbyist.id, client.id)
        representation.add('agent', lobbyist.id)
        representation.add('client', client.id)
        representation.add('role', 'Lobbyist')

        activity_date_start_raw = extract_field_value(activity_block, 'Start date')
        activity_date_start = None
        if activity_date_start_raw:
            activity_date_start = parse_date(activity_date_start_raw[0])
        if activity_date_start:
            representation.add('startDate', activity_date_start)

        activity_date_end_raw = extract_field_value(activity_block, 'End date')
        activity_date_end = None
        if activity_date_end_raw:
            activity_date_end = parse_date(activity_date_end_raw[0])
        if activity_date_end:
            representation.add('endDate', activity_date_end)
        
        arrangement_aim = extract_field_value(activity_block, 'Aim')
        if arrangement_aim:
            representation.add('summary', arrangement_aim)


        representation.add('sourceUrl', article_url)
        
        dataset.emit(representation)




        # Other organisations
        other_orgs_block = get_summary_block(article_soup, 'Organisations involved')
        
        if other_orgs_block:
            org_headers = other_orgs_block.find_all('h3', class_='gi-summary-block__title')

            for other_org in org_headers:
                header_div = other_org.find_parent('div')
                if not header_div:
                    continue

                # Try to extract the actual organisation name from the following rows
                other_lobbyist_name = None
                for row in header_div.find_next_siblings('div'):
                    key = row.find('dt', class_='gi-summary-blocklist__key')
                    if key and key.get_text(strip=True) == 'Name':
                        value = row.find('dd', class_='gi-summary-blocklist__value')
                        if value:
                            p = value.find('p')
                            other_lobbyist_name = p.get_text(strip=True) if p else value.get_text(strip=True)
                        break

                # fallback to header text if Name row not found
                if not other_lobbyist_name:
                    other_lobbyist_name = other_org.get_text(strip=True)

                # Create other lobbyist entity
                other_lobbyist = dataset.make("Company")
                other_lobbyist.id = dataset.make_id('lobbyist', other_lobbyist_name)
                other_lobbyist.add('name', other_lobbyist_name)
                other_lobbyist.add('topics', 'role.lobby')

                dataset.emit(other_lobbyist)

                # Create representation between other lobbyist and client
                other_representation = dataset.make("Representation")
                other_representation.id = dataset.make_id('rep', other_lobbyist.id, client.id)
                other_representation.add('agent', other_lobbyist.id)
                other_representation.add('client', client.id)
                other_representation.add('role', 'Lobbyist')
                other_representation.add('startDate', activity_date_start)
                other_representation.add('endDate', activity_date_end)
                other_representation.add('sourceUrl', article_url)
                dataset.emit(other_representation)

                # Create link between main lobbyist and other lobbyist
                other_link = dataset.make("UnknownLink")
                other_link.id = dataset.make_id('link', lobbyist.id, other_lobbyist.id)
                other_link.add('subject', lobbyist.id)
                other_link.add('object', other_lobbyist.id)
                other_link.add('role', 'Consultant')
                other_link.add('startDate', activity_date_start)
                other_link.add('endDate', activity_date_end)
                other_link.add('sourceUrl', article_url)
                dataset.emit(other_link)


if __name__ == '__main__':
    pass
