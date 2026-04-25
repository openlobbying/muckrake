from .govuk_ministerial import crawl_ministerial_transparency


def get_departments(dataset):
    departments = dataset._data.get("departments", [])
    if not isinstance(departments, list) or not departments:
        raise ValueError("meetings dataset config must define a non-empty 'departments' list")
    for department in departments:
        if not isinstance(department, dict):
            raise ValueError("each meetings department config must be a mapping")
        name = department.get("name")
        collection_urls = department.get("collection_urls")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each meetings department config must define a name")
        if not isinstance(collection_urls, list) or not collection_urls:
            raise ValueError(f"meetings department '{name}' must define collection_urls")
        yield name, collection_urls


def crawl(dataset):
    minister_cache: dict[str, object] = {}
    employment_cache: set[str] = set()
    participant_cache: dict[str, object] = {}

    for department_name, collection_urls in get_departments(dataset):
        crawl_ministerial_transparency(
            dataset,
            collection_urls,
            department_name,
            minister_cache=minister_cache,
            employment_cache=employment_cache,
            participant_cache=participant_cache,
        )
