import requests
from bs4 import BeautifulSoup
import re

BASE_URL = 'https://www.prca.global/professional-lobbying-register'

def decode_cloudflare_email(encoded_string):
    r = int(encoded_string[:2], 16)
    email = ''.join([chr(int(encoded_string[i:i+2], 16) ^ r) for i in range(2, len(encoded_string), 2)])
    return email

def crawl(dataset):
    def get_text_or_none(parent, tag, class_=None, sub_tag=None, sub_class=None, separator=""):
        el = parent.find(tag, class_=class_)
        if not el:
            return None
        if sub_tag:
            el = el.find(sub_tag, class_=sub_class)
            if not el:
                return None
        return el.get_text(separator=separator, strip=True)

    page = 0
    
    while True:
        url = f"{BASE_URL}?page={page}"
        dataset.log.info(f"Fetching lobbying register page {page}: {url}")

        html_text = dataset.fetch_text(url, cache_days=30)
        soup = BeautifulSoup(html_text, 'html.parser')

        panels = soup.find_all('div', class_='panel')
        if not panels:
            break

        for panel in panels:
            lobbyist = dataset.make("Company")

            #name
            lobbyist_name = get_text_or_none(panel, None, 'panel-heading')
            lobbyist.id = dataset.make_id('lobbyist', lobbyist_name)
            lobbyist.add('name', lobbyist_name)

            # second name
            lobbyist_name_second = get_text_or_none(panel, None, 'views-field-display-name', 'h3', 'field-content')
            if lobbyist_name_second and lobbyist_name_second != lobbyist_name:
                lobbyist.add('alias', lobbyist_name_second)
            
            # address
            lobbyist_address = get_text_or_none(panel, None, 'views-field-address-es-in-the-uk-270', 'span', 'field-content', separator='\n')
            if lobbyist_address:
                lobbyist.add('address', lobbyist_address)

            # jurisdiction and topics (needed for phone normalization)
            lobbyist.add('jurisdiction', 'gb')
            lobbyist.add('topics', 'role.lobby')

            # dates
            date_start = None
            date_end = None
            period_text = get_text_or_none(panel, None, 'views-field-register-period-268', 'span', 'field-content')
            if period_text:
                # Parse format like "2025 Q3 (July, Aug, Sept)"
                match = re.search(r'(\d{4})\s+Q(\d)', period_text)
                if match:
                    year = match.group(1)
                    quarter = int(match.group(2))
                    # Map quarter to start and end months
                    quarter_months = {
                        1: (1, 3),   # Q1: Jan-Mar
                        2: (4, 6),   # Q2: Apr-Jun
                        3: (7, 9),   # Q3: Jul-Sep
                        4: (10, 12)  # Q4: Oct-Dec
                    }
                    if quarter in quarter_months:
                        start_month, end_month = quarter_months[quarter]
                        date_start = f"{year}-{start_month:02d}"
                        date_end = f"{year}-{end_month:02d}"

            # contact details
            contact_el = panel.find(class_='views-field-contact-details-271')
            if contact_el:
                span = contact_el.find('span', class_='field-content')
                if span:
                    contact_text = span.get_text(separator=' ', strip=True)

                    # prefer explicit anchors when present
                    for a in span.find_all('a', href=True):
                        href = str(a.get('href', ''))
                        if href.startswith('mailto:'):
                            lobbyist.add('email', a.get_text(strip=True) or href.split(':', 1)[1])
                        elif 'email-protection' in href and '#' in href:
                            encoded = href.split('#')[1]
                            lobbyist.add('email', decode_cloudflare_email(encoded))
                        elif href.startswith('http') or href.startswith('www'):
                            lobbyist.add('website', href.strip())

                    # Check for cf_email span specifically
                    cf_email = span.find(class_='__cf_email__')
                    if cf_email and cf_email.get('data-cfemail'):
                        lobbyist.add('email', decode_cloudflare_email(cf_email['data-cfemail']))

                    # fallbacks from plain text
                    if not lobbyist.has('email'):
                        m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', contact_text)
                        if m:
                            lobbyist.add('email', m.group(0))

                    if not lobbyist.has('website'):
                        m = re.search(r'(https?://\S+|www\.\S+)', contact_text)
                        if m:
                            lobbyist.add('website', m.group(0))

                    # phone: look for digit sequences with spaces, +, -, parentheses
                    p = re.search(r'(?:(?:\(?(?:0(?:0|11)\)?[\s-]?\(?|\+)44\)?[\s-]?(?:\(?0\)?[\s-]?)?)|(?:\(?0))(?:(?:\d{5}\)?[\s-]?\d{4,5})|(?:\d{4}\)?[\s-]?(?:\d{5}|\d{3}[\s-]?\d{3}))|(?:\d{3}\)?[\s-]?\d{3}[\s-]?\d{3,4})|(?:\d{2}\)?[\s-]?\d{4}[\s-]?\d{4}))(?:[\s-]?(?:x|ext\.?|\#)\d{3,4})?', contact_text)
                    if p:
                        lobbyist.add('phone', p.group(0).strip())

            dataset.emit(lobbyist)

            # Get practitioners
            pract_el = panel.find(class_='views-field-practitioners-employed-and-sub-c-273')
            if pract_el:
                span = pract_el.find('span', class_='field-content')
                if span:
                    text = span.get_text(separator='\n', strip=True)
                    for name in (n.strip() for n in text.splitlines()):
                        if name:
                            # Create practitioner entity
                            practitioner = dataset.make("Person")
                            practitioner.id = dataset.make_id(lobbyist_name, name)
                            practitioner.add('name', name)
                            practitioner.add('topics', 'role.lobby')
                            practitioner.add('jurisdiction', 'gb')
                            dataset.emit(practitioner)

                            # Link practitioner to lobbyist
                            practitioner_employment = dataset.make("Employment")
                            practitioner_employment.id = dataset.make_id(practitioner.id, lobbyist.id)
                            practitioner_employment.add('employer', lobbyist.id)
                            practitioner_employment.add('employee', practitioner.id)
                            practitioner_employment.add('startDate', date_start)
                            # practitioner_employment.add('endDate', date_end) # latest quarter should have no end date
                            dataset.emit(practitioner_employment)
            
            # Get clients from all three sources
            client_classes = [
                'views-field-consultancy-services-clients-275',
                'views-label-monitoring-services-clients-276',
                'views-field-pro-bono-clients-277'
            ]
            
            for client_class in client_classes:
                clients_el = panel.find(class_=client_class)
                if clients_el:
                    span = clients_el.find('span', class_='field-content')
                    if span:
                        text = span.get_text(separator='\n', strip=True)
                        for client_name in (n.strip() for n in text.splitlines()):
                            if client_name and client_name != 'N/A':
                                # Create client entity
                                client = dataset.make("Organization")
                                client.id = dataset.make_id(client_name)
                                client.add('name', client_name)
                                client.add('jurisdiction', 'gb')
                                dataset.emit(client)

                                # Link lobbyist to client
                                lobbying_service = dataset.make("Representation")
                                lobbying_service.id = dataset.make_id(lobbyist.id, client.id)
                                lobbying_service.add('agent', lobbyist.id)
                                lobbying_service.add('client', client.id)
                                lobbying_service.add('role', 'Lobbyist')
                                lobbying_service.add('startDate', date_start)
                                lobbying_service.add('endDate', date_end)
                                dataset.emit(lobbying_service)

        page += 1


if __name__ == '__main__':
    pass
