import csv
from os import path
from bs4 import BeautifulSoup

def clean_html(text):
    if text is None or text == '':
        return text
    if '<' not in text and '&' not in text:
        return text
    return BeautifulSoup(text, 'html.parser').get_text(separator=' ', strip=True)

def crawl(dataset):
    people_url = "https://github.com/sophieehill/my-little-crony/raw/refs/heads/main/people.csv"

    people_path = dataset.fetch_resource("people.csv", people_url)

    with open(people_path, 'r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            entity_name = row.get('id')
            entity_type = row.get('type')
            entity_description = clean_html(row.get('desc'))

            # Create Entity
            entity_schema = 'LegalEntity'
            if entity_type in ('person', 'person '):
                entity_schema = 'Person'
            elif entity_type == 'firm':
                entity_schema = 'Company'
            elif entity_type in ('political party', 'political campaign', 'charity', 'think tank', 'group', 'news', 'church', 'horse'):
                entity_schema = 'Organization'
            elif entity_type in ('government', 'NHS', 'tax haven'):
                entity_schema = 'PublicBody'

            entity = dataset.make(entity_schema)
            entity.id = dataset.make_id(entity_name)
            entity.add('name', entity_name)
            entity.add('summary', entity_description)

            if entity_type == 'political party':
                entity.add('topics', 'pol.party')
            elif entity_type in ('government', 'tax haven', 'NHS'):
                entity.add('topics', 'gov')
            elif entity_type == 'NHS':
                entity.add('topics', 'health')
            elif entity_type == 'news':
                entity.add('topics', 'role.journo')
            elif entity_type == 'church':
                entity.add('topics', 'gov.religion')

            dataset.emit(entity)
    

    connections_url = "https://github.com/sophieehill/my-little-crony/raw/refs/heads/main/connections.csv"

    connections_path = dataset.fetch_resource("connections.csv", connections_url)

    with open(connections_path, 'r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            connection_from = row.get('from')
            connection_to = row.get('to')
            connection_detail = clean_html(row.get('detail'))
            connection_type = row.get('type')
            # parse contract_size safely: treat empty/non-numeric as missing
            raw_size = row.get('contract_size')
            connection_contract_size = None
            if raw_size:
                try:
                    clean = str(raw_size).strip().replace(',', '').replace('£', '').replace('$', '')
                    if clean != '':
                        connection_contract_size = int(float(clean) * 1000)
                except Exception:
                    connection_contract_size = None

            if connection_type in ('member', 'group'):
                connection = dataset.make('Membership')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('member', dataset.make_id(connection_from))
                connection.add('organization', dataset.make_id(connection_to))
                connection.add('summary', connection_detail)
                dataset.emit(connection)

            elif connection_type == 'corporate':
                connection = dataset.make('Ownership')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('owner', dataset.make_id(connection_from))
                connection.add('asset', dataset.make_id(connection_to))
                connection.add('summary', connection_detail)
                dataset.emit(connection)

            elif connection_type == 'job':
                connection = dataset.make('Employment')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('employer', dataset.make_id(connection_to))
                connection.add('employee', dataset.make_id(connection_from))
                connection.add('summary', connection_detail)
                dataset.emit(connection)

            elif connection_type == 'donor':
                connection = dataset.make('Payment')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('payer', dataset.make_id(connection_to))
                connection.add('beneficiary', dataset.make_id(connection_from))
                if connection_contract_size is not None:
                    connection.add('amount', connection_contract_size)
                    connection.add('currency', 'GBP')
                connection.add('summary', connection_detail)
                dataset.emit(connection)
            
            elif connection_type == 'contract':
                connection = dataset.make('Contract')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('authority', dataset.make_id(connection_to))
                if connection_contract_size is not None:
                    connection.add('amount', connection_contract_size)
                    connection.add('currency', 'GBP')
                connection.add('summary', connection_detail)
                
                connection_award = dataset.make('ContractAward')
                connection_award.id = dataset.make_id('award', connection_from, connection_to, connection_type)
                connection_award.add('supplier', dataset.make_id(connection_from))
                connection_award.add('contract', connection.id)
                if connection_contract_size is not None:
                    connection_award.add('amount', connection_contract_size)
                    connection_award.add('currency', 'GBP')
                connection_award.add('summary', connection_detail)
                dataset.emit(connection_award)

            elif connection_type == 'family':
                connection = dataset.make('Family')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('person', dataset.make_id(connection_from))
                connection.add('relative', dataset.make_id(connection_to))
                connection.add('summary', connection_detail)
                dataset.emit(connection)

            elif connection_type == 'meeting':
                connection = dataset.make('Event')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('organizer', dataset.make_id(connection_to))
                connection.add('involved', dataset.make_id(connection_from))
                connection.add('summary', connection_detail)
                dataset.emit(connection)
            
            # skip
            elif connection_type in ('jurisdiction', 'regulatory'):
                continue
            # connection, informal, financial
            else:
                connection = dataset.make('UnknownLink')
                connection.id = dataset.make_id(connection_from, connection_to, connection_type)
                connection.add('subject', dataset.make_id(connection_from))
                connection.add('object', dataset.make_id(connection_to))
                connection.add('summary', connection_detail)
                dataset.emit(connection)
            
if __name__ == '__main__':
    pass