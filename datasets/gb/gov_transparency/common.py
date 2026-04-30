import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def load_sibling_module(current_file: str, current_name: str, name: str):
    spec = importlib.util.spec_from_file_location(
        f"{current_name}.{name}",
        Path(current_file).with_name(f"{name}.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load gov-transparency {name} module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalise_marker(value: str) -> str:
    return value.strip().casefold()


def should_skip_row(values: list[str], skip_row_prefixes: list[str]) -> bool:
    if not skip_row_prefixes:
        return False
    normalised_values = [normalise_marker(value) for value in values if value.strip()]
    if not normalised_values:
        return False
    normalised_prefixes = [normalise_marker(prefix) for prefix in skip_row_prefixes if prefix.strip()]
    return any(value.startswith(prefix) for value in normalised_values for prefix in normalised_prefixes)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def month_last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year + (month // 12), (month % 12) + 1, 1) - date.resolution).day


def parse_period(title: str) -> tuple[date | None, date | None]:
    text = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", title)).strip()
    if not text:
        return None, None

    range_match = re.search(
        r"(?P<start_day>\d{1,2})?\s*(?P<start_month>[A-Za-z]+)(?:\s+(?P<start_year>\d{4}))?\s+to\s+"
        r"(?P<end_day>\d{1,2})?\s*(?P<end_month>[A-Za-z]+)\s+(?P<end_year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if range_match is not None:
        start_month = MONTH_NAMES.get(range_match.group("start_month").lower())
        end_month = MONTH_NAMES.get(range_match.group("end_month").lower())
        if start_month is None or end_month is None:
            return None, None
        end_year = int(range_match.group("end_year"))
        start_year_text = range_match.group("start_year")
        if start_year_text is None:
            start_year = end_year - 1 if start_month > end_month else end_year
        else:
            start_year = int(start_year_text)
        start_day = int(range_match.group("start_day") or 1)
        end_day = int(range_match.group("end_day") or month_last_day(end_year, end_month))
        start_day = min(start_day, month_last_day(start_year, start_month))
        end_day = min(end_day, month_last_day(end_year, end_month))
        return date(start_year, start_month, start_day), date(end_year, end_month, end_day)

    month_match = re.search(
        r"(?P<start_month>[A-Za-z]+)(?:\s+to)?\s+(?P<end_month>[A-Za-z]+)\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if month_match is None:
        return None, None
    year = int(month_match.group("year"))
    start_month = MONTH_NAMES.get(month_match.group("start_month").lower())
    end_month = MONTH_NAMES.get(month_match.group("end_month").lower())
    if start_month is None or end_month is None:
        return None, None
    return date(year, start_month, 1), date(year, end_month, month_last_day(year, end_month))
