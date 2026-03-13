import json
import logging
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

def crawl(dataset):
    url = "https://influenceindustry.org/en/explorer/companies/"
    html = dataset.fetch_text(url, cache_days=30)

    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        dataset.log.error("Could not find __NEXT_DATA__ script tag")
        return

    try:
        data = json.loads(script.string)
        companies = data.get("props", {}).get("pageProps", {}).get("companies", [])
    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        dataset.log.error(f"Failed to parse company data: {e}")
        return

    dataset.log.info(f"Processing {len(companies)} companies found on page")

    count = 0
    for item in companies:
        title = item.get("title")
        uuid = item.get("uuid")
        
        if not title or not uuid:
            continue

        # Filtering for UK
        # We include companies that are either registered in the UK (OpenCorporates ID)
        # or have evidence of activity in the UK (GB country code in evidence).
        is_uk = False
        oc_id = item.get("openCorporatesId", "")
        if oc_id and oc_id.lower().startswith("gb/"):
            is_uk = True
        
        if not is_uk:
            for evidence in item.get("evidence", []):
                countries = evidence.get("countries", [])
                if countries and "GB" in countries:
                    is_uk = True
                    break
        
        if not is_uk:
            continue
            
        # We use 'Company' as the schema because these are influence industry firms.
        entity = dataset.make("Company")
        # Use the provided UUID to ensure stable IDs across crawls.
        entity.id = dataset.make_id(uuid)
        entity.add("name", title)
        entity.add("summary", item.get("description"))
        entity.add("website", item.get("website"))
        
        if oc_id:
            # The USER requested to use opencorporatesUrl instead of opencorporatesCode
            entity.add("opencorporatesUrl", oc_id)
            
        for alias in item.get("alternativeNames", []):
            entity.add("alias", alias)
            
        # Add the country code for the United Kingdom.
        entity.add("country", "gb")
        
        # Extract keywords from evidence categories.
        categories = set()
        for evidence in item.get("evidence", []):
            for cat in evidence.get("categories", []):
                if cat:
                    categories.add(cat.strip())
            
            # If the evidence provides a specific description for the work done,
            # we can add it as a note to the entity.
            evidence_desc = evidence.get("description")
            if evidence_desc:
                entity.add("notes", evidence_desc)
        
        for category in categories:
            entity.add("keywords", category)

        dataset.emit(entity)
        count += 1

    dataset.log.info(f"Successfully processed {count} companies matching UK criteria.")

if __name__ == "__main__":
    # This allows running the script directly for testing if needed, 
    # though it's designed to be called by muckrake's crawl runner.
    pass
