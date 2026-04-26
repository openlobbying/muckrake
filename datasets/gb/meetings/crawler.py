import logging
import os
from datetime import date

from .govuk_ministerial import crawl_ministerial_transparency
from .validation import MeetingsValidation


def parse_config_date(value, department_name: str, field_name: str):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"meetings department '{department_name}' must define {field_name} as an ISO date string"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"meetings department '{department_name}' has invalid {field_name}: {value}"
        ) from exc


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
        if not isinstance(collection_urls, list):
            raise ValueError(f"meetings department '{name}' must define collection_urls as a list")

        normalized_urls = []
        for url in collection_urls:
            if not isinstance(url, str):
                raise ValueError(
                    f"meetings department '{name}' collection_urls must contain only strings"
                )
            url = url.strip()
            if url:
                normalized_urls.append(url)

        start_date = parse_config_date(department.get("start_date"), name, "start_date")
        end_date = parse_config_date(department.get("end_date"), name, "end_date")
        if start_date is not None and end_date is not None and end_date <= start_date:
            raise ValueError(
                f"meetings department '{name}' must have end_date after start_date"
            )
        if not normalized_urls:
            continue

        yield {
            "name": name.strip(),
            "collection_urls": normalized_urls,
            "start_date": start_date,
            "end_date": end_date,
        }


def crawl(dataset):
    logging.getLogger("muckrake.extract.fetch").setLevel(logging.WARNING)
    logging.getLogger("muckrake.crawl").setLevel(logging.WARNING)

    minister_cache: dict[str, object] = {}
    employment_cache: set[str] = set()
    participant_cache: dict[str, object] = {}
    validator = MeetingsValidation()
    department_filter = os.getenv("MUCKRAKE_MEETINGS_DEPARTMENT")

    for department in get_departments(dataset):
        if department_filter and department["name"] != department_filter:
            continue
        crawl_ministerial_transparency(
            dataset,
            department["collection_urls"],
            department["name"],
            minister_cache=minister_cache,
            employment_cache=employment_cache,
            participant_cache=participant_cache,
            start_date=department["start_date"],
            end_date=department["end_date"],
            validator=validator,
        )

    validator.log_summary()
