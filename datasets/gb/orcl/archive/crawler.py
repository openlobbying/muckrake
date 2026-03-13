import pandas as pd
from bs4 import BeautifulSoup
import re
from pathlib import Path
from muckrake.dataset import Dataset
from muckrake.util import month_to_num, to_string
import requests

SOURCE_URL = "https://orcl.my.site.com/CLR_Annual_Returns_Downloads"

def crawl(context: Dataset):
    context.log.info("Starting ORCL crawl")
    
    # 1. Scrape links
    res = requests.get(SOURCE_URL)
    res.raise_for_status()
    soup = BeautifulSoup(res.content, "lxml")
    
    links = []
    for a in soup.select(".downloadDropdown li a"):
        title = a.get_text(strip=True)
        url = a.get("href")
        if not url:
            continue
        
        # Parse date from title - try multiple patterns
        date_str = None
        
        # Pattern 1: "October to December 2024"
        match = re.search(r"(\w+)\s+to\s+(\w+)\s+(\d{4})", title)
        if match:
            start_month, end_month, year = match.groups()
            if int(year) < 2014:
                continue
            month_num = month_to_num(start_month) or "01"
            date_str = f"{year}-{month_num}-01"
        
        # Pattern 2: "Quarter One (January-March 2015)" or similar
        if not date_str:
            match = re.search(r"Quarter\s+\w+\s*\((\w+)[^)]*(\d{4})\)", title, re.IGNORECASE)
            if match:
                month, year = match.groups()
                if int(year) < 2014:
                    continue
                month_num = month_to_num(month) or "01"
                date_str = f"{year}-{month_num}-01"
        
        # Pattern 3: Just year and month somewhere in the title
        if not date_str:
            match = re.search(r"(\w+)\s+(\d{4})", title)
            if match:
                month, year = match.groups()
                if int(year) < 2014:
                    continue
                month_num = month_to_num(month)
                if month_num:
                    date_str = f"{year}-{month_num}-01"
        
        # Skip if we couldn't parse a valid date
        if not date_str:
            context.log.warning(f"Could not parse date from title: {title}")
            continue

        ext = "xlsx" if "Excel" in title or url.endswith(".xlsx") else "csv"
        links.append({
            "title": title,
            "url": url,
            "date": date_str,
            "ext": ext
        })

    # 2. Download and process - collect all relationships first
    all_relationships = []
    for link in links:
        # Special case from R script for 2024-10-01
        if link["date"] == "2024-10-01":
            url = "https://registrarofconsultantlobbyists.org.uk/wp-content/uploads/2025/01/October-to-December-2024-QIR-Report-Excel-44Kb.xlsx"
        else:
            url = link["url"]
        
        filename = f"{link['date']}.{link['ext']}"
        path = context.fetch_resource(filename, url)

        relationships = process_file(context, path, link["date"])
        all_relationships.extend(relationships)
    
    # 3. Aggregate and emit relationships
    aggregate_and_emit(context, all_relationships)

def process_file(context: Dataset, path: Path, date: str):
    """Process a single file and return list of relationships."""
    context.log.info(f"Processing {path.name}")
    
    relationships = []
    
    try:
        if path.suffix == ".xlsx":
            # The R script has complex skip logic based on date.
            # We'll try to guess based on date or just look for headers.
            # Default skip is often 0 but script has 2, 7, 8, 10.
            # Let's try to read it and find where "Lobbyist" or "Firm" headers are.
            df = pd.read_excel(path)
            
            # Find the header row by looking for "Lobbyist" or "Consultant"
            header_idx = -1
            for i, row in df.iterrows():
                row_str = " ".join(str(x) for x in row.values).lower()
                if "consultant lobbyist" in row_str or "lobbying firm" in row_str:
                    header_idx = i
                    break
            
            if header_idx != -1:
                df = pd.read_excel(path, skiprows=header_idx + 1)
        else:
            df = pd.read_csv(path)
    except Exception as e:
        context.log.error(f"Error reading {path}: {e}")
        return relationships

    # Normalize columns
    # We expect 1st column to be Lobbyist, 2nd to be Client (usually)
    # R script says: select(date, lobby_firm = 1, org = 2)
    if len(df.columns) < 2:
        return relationships
        
    for _, row in df.iterrows():
        lobby_firm_name = to_string(row.iloc[0])
        client_name = to_string(row.iloc[1])
        
        if not lobby_firm_name or not client_name:
            continue
        
        relationships.append({
            "lobbyist": lobby_firm_name,
            "client": client_name,
            "date": date
        })
    
    return relationships

def aggregate_and_emit(context: Dataset, relationships):
    """Aggregate consecutive quarterly relationships and emit entities."""
    if not relationships:
        return
    
    # Convert to DataFrame for easier processing
    df = pd.DataFrame(relationships)
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d')
    df = df.sort_values(['lobbyist', 'client', 'date'])
    
    context.log.info(f"Aggregating {len(df)} relationships")
    
    # Find the latest quarter in the entire dataset
    latest_date = df['date'].max()
    context.log.info(f"Latest quarter in dataset: {latest_date.strftime('%Y-%m-%d')}")
    
    # Process each firm-client pair
    for (lobbyist, client), group in df.groupby(['lobbyist', 'client']):
        # Emit firm entity
        firm = context.make("LegalEntity")
        firm.id = context.make_id("firm", lobbyist)
        firm.add("name", lobbyist)
        context.emit(firm)
        
        # Emit client entity
        org = context.make("LegalEntity")
        org.id = context.make_id("client", client)
        org.add("name", client)
        context.emit(org)
        
        # Merge consecutive quarters into date ranges
        dates = sorted(group['date'].tolist())
        periods = []
        current_start = dates[0]
        current_end = dates[0]
        
        for i in range(1, len(dates)):
            # Check if next date is within ~3 months (quarterly)
            expected_next = current_end + pd.DateOffset(months=3)
            # Allow 5 days tolerance for date variations
            if dates[i] <= expected_next + pd.Timedelta(days=5):
                current_end = dates[i]
            else:
                # Gap detected, save current period and start new one
                periods.append((current_start, current_end))
                current_start = dates[i]
                current_end = dates[i]
        
        # Add the last period
        periods.append((current_start, current_end))
        
        # Emit a Representation for each continuous period
        for start_date, end_date in periods:
            rel = context.make("Representation")
            rel.id = context.make_id("rel", lobbyist, client, start_date.strftime('%Y-%m-%d'))
            rel.add("agent", firm.id)
            rel.add("client", org.id)
            rel.add("role", "Consultant Lobbyist")
            rel.add("sourceUrl", SOURCE_URL)
            
            # Set date range - use quarter start for startDate
            quarter_start = start_date.to_period('Q').to_timestamp()
            rel.add("startDate", quarter_start.strftime('%Y-%m-%d'))
            
            # Only add endDate if this period doesn't extend to the latest quarter
            # (if it does, the relationship is still ongoing)
            if end_date < latest_date:
                quarter_end = end_date.to_period('Q').to_timestamp(how='end')
                rel.add("endDate", quarter_end.strftime('%Y-%m-%d'))
            
            context.emit(rel)
