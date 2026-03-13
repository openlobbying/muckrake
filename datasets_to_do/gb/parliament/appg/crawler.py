from urllib.parse import urljoin

def crawl(dataset):

    URL = "https://www.parliament.uk/mps-lords-and-offices/standards-and-financial-interests/parliamentary-commissioner-for-standards/registers-of-interests/register-of-all-party-party-parliamentary-groups/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-GB',
        # 'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Referer': 'https://appg.castfromclay.co.uk/',
        'DNT': '1',
        'Alt-Used': 'www.parliament.uk',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'If-Modified-Since': 'Sat, 10 Jan 2026 00:08:46 GMT',
        'Priority': 'u=0, i',
    }

    # extract links to the years
    page_years = dataset.fetch_html(URL, headers=headers, cache_days=7)
    if page_years is None:
        dataset.log.error("Failed to fetch APPG register page")
        return
    
    years_main_bodies = page_years.xpath('.//*[@class="main-body"]')
    if len(years_main_bodies) == 0:
        dataset.log.error("Failed to find main-body in APPG register page")
        return
    main_body = years_main_bodies[0]
    
    year_links = main_body.xpath(".//a")
    for link in year_links:
        # extract register versions
        link_url = urljoin(URL, link.get('href'))
        page_versions = dataset.fetch_html(link_url, headers=headers, cache_days=7)
        if page_versions is None:
            dataset.log.error(f"Failed to fetch APPG register page: {link_url}")
            continue

        for version in page_versions.xpath('.//a[text()="HTML Version"]'):
            version_url = urljoin(link_url, version.get("href"))
            # dataset.log.info(f"Crawling APPG register version: {version_url}")

            # extract the list of APPGs from the version page
            page_appgs = dataset.fetch_html(version_url, headers=headers, cache_days=7)
            if page_appgs is None:
                dataset.log.error(f"Failed to fetch APPG register version page: {version_url}")
                continue
            appg_links = page_appgs.xpath('//*[@id="mainTextBlock"]//li/a/@href')
            dataset.log.info(f"Found {len(appg_links)} APPGs in version: {version_url}")

            for appg_link in appg_links:
                appg_url = urljoin(version_url, appg_link)
                dataset.download_file(appg_url, prefix="appg/")
            



if __name__ == "__main__":
    pass