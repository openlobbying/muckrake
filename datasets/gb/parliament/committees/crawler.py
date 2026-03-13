from ..util import make_committee

def crawl(dataset):

    BASE_URL = "https://committees-api.parliament.uk/api/Committees"

    PARAMS = {
        "skip": 0,
        "take": 30,
        "CommitteeStatus": "All"
    }

    while True:
        dataset.log.info(f"Crawling committees with params: {PARAMS}")
        data = dataset.fetch_json(BASE_URL, params=PARAMS, cache_days=7)
        if data is None:
            break

        items = data.get('items', [])
        if not items:
            break

        for item in items:
            make_committee(dataset, item)

        PARAMS['skip'] += PARAMS['take']

if __name__ == "__main__":
    pass