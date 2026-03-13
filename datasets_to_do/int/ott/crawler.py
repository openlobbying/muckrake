import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urljoin

BASE_URL = "https://onthinktanks.org/open-think-tank-directory/"
    
PARAMS = {
    "select-ottd_country[]": "united-kingdom",
    "hidden-s-": "",
    "hidden-current-page": "1"
}

def clean_text(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text if text else None

def parse_year(text: str) -> str | None:
    if not text:
        return None
    # match 4 digits
    match = re.search(r'\d{4}', text)
    if match:
        return match.group(0)
    return None

def crawl(dataset):
    
    current_page = 1
    
    while True:
        PARAMS["hidden-current-page"] = str(current_page)
        query_string = urlencode(PARAMS)
        url = f"{BASE_URL}?{query_string}"
        
        dataset.log.info(f"Crawling page {current_page}: {url}")

        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        listings = soup.select('div#js-search-listing a.c-card__content')
        
        if not listings:
            break

        for link_tag in listings:
            link = link_tag.get("href")
            if not link:
                continue

            try:
                link_response = requests.get(link)
                link_soup = BeautifulSoup(link_response.text, 'html.parser')

                # Create Organization entity
                org = dataset.make("Organization")

                # get name and acronym
                name_el = link_soup.select_one("h1.c-single-header__title")
                if not name_el:
                    continue
                name = clean_text(name_el.get_text())

                org.id = dataset.make_id("thinktank", name)
                org.add("name", name)
                
                acronym = None
                acronym_el = link_soup.select_one("div.c-single-header__subtitle")
                if acronym_el:
                    acronym = clean_text(acronym_el.get_text())
                
                if acronym:
                    org.add("weakAlias", acronym) # TODO: figure out why "abbreviation" is not accepted

                # description
                desc = None
                desc_el = link_soup.select_one("div.c-single--directory__description")
                if desc_el:
                    desc = clean_text(desc_el.get_text())
                
                org.add("summary", desc)
                org.add("topics", "pol.thinktank")
                org.add("sourceUrl", link)

                # Parse Definition List for contact info
                dl = link_soup.select_one("dl.c-single--directory__section-data-dl")
                if dl:
                    for dt in dl.select("dt"):
                        label = clean_text(dt.get_text())
                        dd = dt.find_next_sibling("dd")
                        val = clean_text(dd.get_text()) if dd else None
                        
                        if not val:
                            continue
                            
                        if "Website" in label:
                            website = dd.find("a").get("href") if dd.find("a") else val
                            org.add("website", website)
                        if "Address" in label:
                            org.add("address", val)
                        if "Country" in label:
                            org.add("country", val)
                
                # Parse Year founded
                # Using a more generic search for section titles as layout relies on h2 and grid structure
                # We can iterate through "c-single--directory__section-data-item" looking for titles
                
                for item in link_soup.select("div.c-single--directory__section-data-item"):
                    sub_title = item.select_one("div.c-single--directory__section-sub-title")
                    if not sub_title:
                        continue
                        
                    title_text = clean_text(sub_title.get_text()) or ""
                    
                    data_el = item.select_one("div.c-single--directory__section-data")
                    sub_data_el = item.select_one("div.c-single--directory__section-sub-data")
                    
                    # Year founded
                    if "Year founded" in title_text and data_el:
                        year = parse_year(data_el.get_text())
                        if year:
                            org.add("incorporationDate", year)
                            
                    # Founded by
                    if "Founded by" in title_text and sub_data_el:
                        founders_text = sub_data_el.get_text(separator="\n").strip()
                        
                        if "Founders:" in founders_text:
                            # Split after "Founders:"
                            after_prefix = founders_text.split("Founders:", 1)[1]
                            
                            # Remove gender info if present
                            name_part = after_prefix.split("Founder gender:", 1)[0]
                            
                            # Replace newlines with spaces to handle wrapping names, then split by comma
                            name_part = name_part.replace("\n", " ").strip()
                            
                            founder_names = [n.strip() for n in name_part.split(",") if n.strip()]
                            
                            for f_name in founder_names:
                                if f_name.lower() == "n/a":
                                    continue
                                    
                                person = dataset.make("Person")
                                person.id = dataset.make_id("person", f_name)
                                person.add("name", f_name)
                                dataset.emit(person)
                                
                                rel = dataset.make("Directorship")
                                rel.id = dataset.make_id("founder", org.id, person.id)
                                rel.add("organization", org)
                                rel.add("director", person)
                                rel.add("role", "Founder")
                                dataset.emit(rel)

                    # Leadership
                    if "Leadership" in title_text and sub_data_el:
                        for entry in sub_data_el.select("span.c-single--directory__section-sub-data-item"):
                            txt = entry.get_text(separator="\n").strip()
                            if not txt:
                                continue
                            
                            match_iter = re.finditer(r"Leader\(s\)\s*\((\d{4})\):", txt)
                            
                            for match in match_iter:
                                year = match.group(1)
                                start_idx = match.end()
                                
                                remainder = txt[start_idx:]
                                
                                if "Leader gender:" in remainder:
                                    remainder = remainder.split("Leader gender:")[0]
                                
                                # Take first line only
                                leader_name = remainder.split("\n")[0].strip()
                                
                                if leader_name and leader_name.lower() != "n/a":
                                    person = dataset.make("Person")
                                    person.id = dataset.make_id("person", leader_name)
                                    person.add("name", leader_name)
                                    dataset.emit(person)
                                    
                                    emp = dataset.make("Employment")
                                    emp.id = dataset.make_id("employment", org.id, person.id, year)
                                    emp.add("employer", org)
                                    emp.add("employee", person)
                                    emp.add("role", "Leader")
                                    emp.add("date", year)
                                    dataset.emit(emp)

                dataset.emit(org)

            except Exception as e:
                dataset.log.error(f"Failed to process link {link}: {e}")
                continue
        
        current_page += 1
        # Hard limit to avoid infinite loops if pagination detection fails or is infinite
        if current_page > 50: 
            break

if __name__ == "__main__":
    pass