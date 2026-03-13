import requests
from bs4 import BeautifulSoup
import re
import csv
import time

def extract_data(soup):
    results = []
    table = soup.find("table", class_="clrDataTable")
    if not table:
        return results
    
    tbody = table.find("tbody")
    if not tbody:
        return results
        
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) >= 2:
            name_cell = cols[0]
            link_cell = cols[1]
            
            name = name_cell.get_text(strip=True)
            link_tag = link_cell.find("a")
            profile_url = ""
            if link_tag:
                profile_url = link_tag.get("href", "")
                if profile_url.startswith("/"):
                    profile_url = "https://orcl.my.site.com" + profile_url
            
            results.append({
                "name": name,
                "profile_url": profile_url
            })
    return results

def scrape():
    url = "https://orcl.my.site.com/CLR_Search"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    all_results = []
    current_url = url
    
    print(f"[*] Fetching Page 1...")
    r = session.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    
    page_data = extract_data(soup)
    all_results.extend(page_data)
    print(f"[*] Page 1: Found {len(page_data)} records (Total: {len(all_results)})")

    page_num = 1
    while True:
        # Check for Next Page link
        next_page_link = soup.find("a", string="Next Page")
        if not next_page_link:
            print("[*] No 'Next Page' link found. Finished.")
            break
            
        onclick = next_page_link.get("onclick", "")
        match = re.search(r"A4J\.AJAX\.Submit\('([^']+)'.*?'parameters':\{'([^']+)':'([^']+)'\}", onclick)
        if not match:
            print("[!] Could not parse Next Page click handler. Stopping.")
            break
            
        container_id = match.group(1)
        link_id = match.group(2)
        
        # Prepare Payload
        payload = {}
        for input_tag in soup.find_all("input", type="hidden"):
            payload[input_tag.get("name")] = input_tag.get("value")
            
        payload["AJAXREQUEST"] = "_viewRoot"
        payload[container_id] = container_id
        payload[link_id] = link_id
        
        ajax_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url,
            "Origin": "https://orcl.my.site.com",
            "Accept": "*/*"
        }
        
        page_num += 1
        print(f"[*] Fetching Page {page_num}...")
        
        # Small delay to be polite
        time.sleep(1)
        
        r = session.post(url, data=payload, headers=ajax_headers)
        if r.status_code != 200:
            print(f"[!] Page {page_num} fetch failed with {r.status_code}")
            break
            
        # The response is XML wrapping XHTML
        # BeautifulSoup can parse it even with the XML declaration
        soup = BeautifulSoup(r.text, "html.parser")
        
        page_data = extract_data(soup)
        if not page_data:
            print(f"[!] No data found on Page {page_num}. Response might be incomplete.")
            # Debug: Save failing response
            with open(f"error_page_{page_num}.xml", "w") as f:
                f.write(r.text)
            break
            
        all_results.extend(page_data)
        print(f"[*] Page {page_num}: Found {len(page_data)} records (Total: {len(all_results)})")
        
    # Save to CSV
    with open("lobbyists.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "profile_url"])
        writer.writeheader()
        writer.writerows(all_results)
    
    print(f"[*] Done! Saved {len(all_results)} records to lobbyists.csv")

if __name__ == "__main__":
    scrape()
