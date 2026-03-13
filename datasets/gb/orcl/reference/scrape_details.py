import requests
from bs4 import BeautifulSoup
import re
import csv
import time
import os

def extract_details(soup):
    details = {
        "address": "",
        "company_number": "",
        "clients": ""
    }
    
    # 1. Address
    # Structure: <h3>Address</h3> <p>line 1<br>line 2<br>...</p>
    address_h3 = soup.find("h3", string=re.compile(r"Address", re.I))
    if address_h3:
        address_p = address_h3.find_next_sibling("p")
        if address_p:
            # Drop any script tags inside
            for script in address_p.find_all("script"):
                script.decompose()
            # Get text parts separated by br
            addr_text = address_p.get_text(separator=" ", strip=True)
            details["address"] = addr_text

    # 2. Company Number
    # Structure: <label class="heading-medium">Company Number</label> 924113
    company_label = soup.find("label", string=re.compile(r"Company Number", re.I))
    if company_label:
        # It's often a text node after the label
        next_sibling = company_label.next_sibling
        if next_sibling and isinstance(next_sibling, str):
            details["company_number"] = next_sibling.strip()
        else:
            # Fallback check next elements
            details["company_number"] = company_label.get_text(strip=True).replace("Company Number", "").strip()

    # 3. Client List
    # Structure: table.clrDataTable under "Current client list"
    clients = []
    # Find the current client list section
    current_list_heading = soup.find(string=re.compile(r"Current client list", re.I))
    if current_list_heading:
        # The table is a sibling of the parent or nearby
        parent = current_list_heading.parent
        # Try to find the first table following this heading
        table = current_list_heading.find_next("table", class_="clrDataTable")
        if table:
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                for col in cols:
                    text = col.get_text(strip=True)
                    if text and text.lower() != "client":
                        clients.append(text)
    
    details["clients"] = "; ".join(clients)
    
    return details

def scrape_profiles(limit=None):
    if not os.path.exists("lobbyists.csv"):
        print("[!] lobbyists.csv not found. Run the initial scraper first.")
        return

    with open("lobbyists.csv", "r") as f:
        reader = list(csv.DictReader(f))
        
    if limit:
        reader = reader[:limit]
        
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    results = []
    total = len(reader)
    
    for i, row in enumerate(reader):
        name = row["name"]
        url = row["profile_url"]
        
        if not url:
            results.append({**row, "address": "", "company_number": "", "clients": ""})
            continue
            
        print(f"[*] [{i+1}/{total}] Scraping details for: {name}")
        try:
            r = session.get(url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                details = extract_details(soup)
                results.append({**row, **details})
            else:
                print(f"    [!] Failed to fetch profile: {r.status_code}")
                results.append({**row, "address": "FAILED", "company_number": "", "clients": ""})
        except Exception as e:
            print(f"    [!] Error: {e}")
            results.append({**row, "address": "ERROR", "company_number": "", "clients": ""})
            
        time.sleep(0.5) # Be kind

    # Save to expanded CSV
    output_file = "lobbyists_detailed.csv"
    if results:
        keys = results[0].keys()
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)
        print(f"[*] Done! Saved {len(results)} detailed records to {output_file}")

if __name__ == "__main__":
    # Test with first 5 profiles
    scrape_profiles(limit=5)
