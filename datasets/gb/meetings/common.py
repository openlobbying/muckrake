import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlparse

import pandas as pd

from muckrake.dataset import Dataset
from muckrake.util import parse_amount, parse_date, to_string

TABULAR_EXTENSIONS = {"csv", "xlsx", "xls"}
HEADER_THRESHOLD = 3
CATEGORY_TRAILING_WINDOW = 40

CATEGORY_KEYWORDS = {
    "meetings": ("meeting",),
    "hospitality": ("hospitality",),
    "gifts": ("gift",),
    "travel": ("travel",),
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

FIELD_ALIASES = {
    "meetings": {
        "minister": [
            "minister",
            "minister name",
            "ministerial name",
            "name of minister",
            "official",
        ],
        "date": ["date", "date of meeting", "meeting date"],
        "counterparty": [
            "name of organisation or individual",
            "name of individual or organisation",
            "name of organisation",
            "name of organization",
            "name of external organisation",
            "name of external organization",
            "external party",
            "organisation individual",
            "organization individual",
            "individual organisation",
            "individual organization",
            "external attendees",
            "attendees external organisation",
            "attendees external organization",
        ],
        "purpose": [
            "purpose of meeting",
            "purpose",
            "subject",
            "details",
            "meeting purpose",
        ],
    },
    "gifts": {
        "minister": ["minister"],
        "date": ["date", "date gift given", "date gift received"],
        "gift": ["gift"],
        "direction": ["given or received"],
        "counterparty": [
            "who gift was given to or received from",
            "to",
            "from",
        ],
        "value": ["value gbp", "value"],
        "outcome": ["outcome received gifts only", "outcome"],
    },
    "hospitality": {
        "minister": ["minister"],
        "date": ["date", "date of hospitality"],
        "counterparty": [
            "person or organisation that offered hospitality",
            "individual or organisation that offered hospitality",
            "name of organisation",
            "name of organization",
        ],
        "kind": [
            "type of hospitality received",
            "type of hospitality received include an asterisk against the entry if accompanied by spouse partner or other family member or friend",
        ],
        "guest": [
            "accompanied by spouse family members or friend",
            "accompanied by guest",
        ],
    },
    "travel": {
        "minister": ["minister"],
        "start_date": ["start date", "start date of trip"],
        "end_date": ["end date", "end date of trip"],
        "date_text": ["dates of trip", "date(s) of trip"],
        "destination": ["destination"],
        "purpose": ["purpose of trip"],
        "transport": [
            "mode of transport",
            "modes of transport",
            "no 32 the royal squadron or other raf or charter or eurostar",
        ],
        "transport_cost": [
            "cost of private jet or raf plane hire if relevant gbp",
            "subtotal of all travel costs including any non scheduled raf flights gbp",
        ],
        "accompanying_officials": [
            "number of officials who accompanied minister if non shceduled travel was used",
            "number of officials who accompanied minister if non scheduled travel was used",
            "number of officials who accompanied the minister if non scheduled flight was taken",
            "number of officials accompanying minister where non scheduled travel is used",
        ],
        "guest": [
            "accompanied by spouse family members or friend at public expense",
            "accompanied by spouse partner at public expense",
        ],
        "associated_cost": [
            "subtotal of associated costs for minister only including all visas accommodation meals etc gbp"
        ],
        "total_cost": [
            "total cost for minister only including all visas accommodation travel meals etc gbp",
            "total cost gbp",
            "total cost including travel and accommodation of minister only",
        ],
    },
}

MINISTER_SECTION_KEYWORDS = (
    "secretary of state",
    "minister of state",
    "parliamentary under secretary",
    "chancellor",
    "chief secretary",
    "financial secretary",
    "economic secretary",
    "exchequer secretary",
    "paymaster general",
    "advocate general",
)

MEETING_NAME_COLUMN = "name"


@dataclass(frozen=True)
class Period:
    start: date
    end: date


@dataclass(frozen=True)
class Publication:
    url: str
    title: str
    period: Optional[Period]


@dataclass(frozen=True)
class TableSource:
    publication: Publication
    category: str
    source_url: str
    title: str
    file_name: str
    frame: pd.DataFrame


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_column_name(value: Any) -> str:
    text = normalize_whitespace(str(value).replace("\n", " "))
    text = re.sub(r"[()\[\]?:,£'*]", "", text)
    text = text.replace("/", " ")
    return normalize_whitespace(text).lower()


def build_normalized_headers(values: Any) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        text = to_string(value)
        if text is None:
            header = f"unnamed {index}"
        else:
            normalized = normalize_column_name(text)
            header = normalized or f"unnamed {index}"
        count = seen.get(header, 0)
        seen[header] = count + 1
        if count:
            header = f"{header} {count + 1}"
        headers.append(header)
    return headers


def is_nil_value(value: Any) -> bool:
    text = to_string(value)
    if text is None:
        return True
    normalized = normalize_whitespace(text).lower().rstrip(".")
    return normalized in {"nil return", "nil", "none", "n/a", "not applicable"}


def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = to_string(value)
    if text is None or is_nil_value(text):
        return None
    return normalize_whitespace(text)


def extract_amount(value: Any) -> Optional[float]:
    text = clean_text(value)
    if text is None:
        return None
    amount = parse_amount(text)
    if amount is not None:
        return amount
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", text.replace(" ", ""))
    if match is None:
        return None
    return parse_amount(match.group(1))


def month_number(value: str) -> Optional[int]:
    return MONTHS.get(value.strip().lower())


def month_last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date.resolution).day


def parse_period(title: str) -> Optional[Period]:
    text = normalize_whitespace(title)
    match = re.search(
        r"(?P<start_day>\d{1,2})?\s*(?P<start_month>[A-Za-z]+)\s+to\s+(?P<end_day>\d{1,2})?\s*(?P<end_month>[A-Za-z]+)\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if match is not None:
        year = int(match.group("year"))
        start_month = month_number(match.group("start_month"))
        end_month = month_number(match.group("end_month"))
        if start_month is None or end_month is None:
            return None
        start_day = min(int(match.group("start_day") or 1), month_last_day(year, start_month))
        end_day = min(
            int(match.group("end_day") or month_last_day(year, end_month)),
            month_last_day(year, end_month),
        )
        return Period(
            start=date(year, start_month, start_day),
            end=date(year, end_month, end_day),
        )

    match = re.search(
        r"(?P<start_month>[A-Za-z]+)-(?P<end_month>[A-Za-z]+)\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if match is not None:
        year = int(match.group("year"))
        start_month = month_number(match.group("start_month"))
        end_month = month_number(match.group("end_month"))
        if start_month is None or end_month is None:
            return None
        return Period(
            start=date(year, start_month, 1),
            end=date(year, end_month, month_last_day(year, end_month)),
        )
    return None


def iter_collection_urls(collection_urls: str | Iterable[str]) -> Iterator[str]:
    if isinstance(collection_urls, str):
        yield collection_urls
        return
    for collection_url in collection_urls:
        if collection_url:
            yield collection_url


def extract_publications(dataset: Dataset, collection_urls: str | Iterable[str]) -> list[Publication]:
    publications: list[Publication] = []
    seen_urls: set[str] = set()
    for collection_url in iter_collection_urls(collection_urls):
        doc = dataset.fetch_html(collection_url, cache_days=30, absolute_links=True)
        for element in doc.xpath("//a[starts-with(@href, 'https://www.gov.uk/government/publications/')]"):
            url = element.get("href")
            if url is None or url in seen_urls:
                continue
            seen_urls.add(url)
            title = normalize_whitespace("".join(element.itertext()))
            publications.append(Publication(url=url, title=title, period=parse_period(title)))
    return publications


def extension_for_url(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower().lstrip(".")


def detect_category(*parts: str) -> Optional[str]:
    def detect_category_part(part: str) -> Optional[str]:
        text = normalize_whitespace(part).lower()
        matches: list[tuple[int, str]] = []
        trailing: list[tuple[int, str]] = []
        for category, keywords in CATEGORY_KEYWORDS.items():
            end_positions = [
                text.rfind(keyword) + len(keyword)
                for keyword in keywords
                if keyword in text
            ]
            if not end_positions:
                continue
            end_position = max(end_positions)
            matches.append((end_position, category))
            if len(text) - end_position <= CATEGORY_TRAILING_WINDOW:
                trailing.append((end_position, category))
        if len(matches) == 1:
            return matches[0][1]
        if len(trailing) == 1:
            return trailing[0][1]
        return None

    for part in parts:
        if not part:
            continue
        category = detect_category_part(part)
        if category is not None:
            return category
    return None


def detect_gift_direction(*parts: str) -> Optional[str]:
    text = " ".join(normalize_whitespace(part).lower() for part in parts if part)
    if "gift received" in text or "gifts received" in text:
        return "Received"
    if "gift given" in text or "gifts given" in text:
        return "Given"
    return None


def score_header_row(values: Any) -> int:
    normalized_values = {
        normalize_column_name(text)
        for value in values
        if (text := to_string(value)) is not None
    }
    best = 0
    for aliases in FIELD_ALIASES.values():
        score = 0
        for candidates in aliases.values():
            if any(candidate in normalized_values for candidate in candidates):
                score += 1
        best = max(best, score)
    return best


def detect_header_row(frame: pd.DataFrame) -> int:
    for index, row in frame.iterrows():
        if score_header_row(row.tolist()) >= HEADER_THRESHOLD:
            return int(index)
    return 0


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized = normalized.dropna(axis=1, how="all")
    normalized = normalized.dropna(axis=0, how="all")
    normalized.columns = build_normalized_headers(normalized.columns)
    if "minister" in normalized.columns:
        normalized["minister"] = normalized["minister"].ffill()
    return normalized.reset_index(drop=True)


def normalize_tabular_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized = normalized.dropna(axis=1, how="all")
    normalized = normalized.dropna(axis=0, how="all")
    if normalized.empty:
        return normalized
    header_row = detect_header_row(normalized)
    headers = build_normalized_headers(normalized.iloc[header_row].tolist())
    normalized = normalized.iloc[header_row + 1 :].copy()
    normalized.columns = headers
    return normalize_frame(normalized)


def normalize_excel_sheet(frame: pd.DataFrame) -> pd.DataFrame:
    return normalize_tabular_frame(frame)


def read_csv_table(
    dataset: Dataset, publication: Publication, file_name: str, source_url: str
) -> pd.DataFrame:
    path = dataset.fetch_resource(f"{Path(publication.url).name}-{file_name}", source_url)
    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            frame = pd.read_csv(path, encoding=encoding, header=None, dtype=object)
            return normalize_tabular_frame(frame)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def read_excel_tables(
    dataset: Dataset, publication: Publication, file_name: str, source_url: str
) -> Iterator[tuple[str, pd.DataFrame]]:
    path = dataset.fetch_resource(f"{Path(publication.url).name}-{file_name}", source_url)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Unknown extension is not supported and will be removed",
            category=UserWarning,
            module=r"openpyxl\.worksheet\._reader",
        )
        with pd.ExcelFile(path) as workbook:
            for sheet_name in workbook.sheet_names:
                frame = pd.read_excel(workbook, sheet_name=sheet_name, header=None, dtype=object)
                normalized = normalize_tabular_frame(frame)
                if normalized.empty:
                    continue
                yield sheet_name, normalized


def detect_field_mapping(category: str, columns: Any) -> dict[str, str]:
    available_columns = list(columns)
    available_set = set(available_columns)
    field_map: dict[str, str] = {}

    for field, candidates in FIELD_ALIASES[category].items():
        for candidate in candidates:
            if candidate in available_set:
                field_map[field] = candidate
                break

    if category != "meetings":
        return field_map

    if "counterparty" not in field_map and MEETING_NAME_COLUMN in available_set:
        minister_column = field_map.get("minister")
        if minister_column is not None and minister_column != MEETING_NAME_COLUMN:
            field_map["counterparty"] = MEETING_NAME_COLUMN

    if "minister" not in field_map and field_map.get("counterparty") is not None:
        counterparty_column = field_map["counterparty"]
        if MEETING_NAME_COLUMN in available_set and counterparty_column != MEETING_NAME_COLUMN:
            field_map["minister"] = MEETING_NAME_COLUMN
        elif available_columns:
            first_column = available_columns[0]
            if isinstance(first_column, str) and first_column.startswith("unnamed"):
                field_map["minister"] = first_column

    return field_map


def iter_publication_tables(
    dataset: Dataset, collection_urls: str | Iterable[str]
) -> Iterator[TableSource]:
    for publication in extract_publications(dataset, collection_urls):
        doc = dataset.fetch_html(publication.url, cache_days=30, absolute_links=True)
        seen_urls: set[str] = set()
        for element in doc.xpath("//a[contains(@href, 'assets.publishing.service.gov.uk')]"):
            source_url = element.get("href")
            if source_url is None or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            ext = extension_for_url(source_url)
            if ext not in TABULAR_EXTENSIONS:
                continue
            title = normalize_whitespace("".join(element.itertext()))
            file_name = Path(urlparse(source_url).path).name
            if ext == "csv":
                category = detect_category(title, file_name, source_url)
                if category is None:
                    continue
                frame = read_csv_table(dataset, publication, file_name, source_url)
                if frame.empty:
                    continue
                yield TableSource(publication, category, source_url, title or file_name, file_name, frame)
                continue
            for sheet_name, frame in read_excel_tables(dataset, publication, file_name, source_url):
                category = detect_category(sheet_name, title, file_name, source_url)
                if category is None:
                    continue
                yield TableSource(publication, category, source_url, sheet_name, file_name, frame)


def parse_cell_date(value: Any) -> Optional[str]:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return parse_date(value)


def parse_month_value(value: str, period: Optional[Period]) -> Optional[tuple[str, str]]:
    cleaned = normalize_whitespace(value)
    match = re.fullmatch(r"([A-Za-z]+)(?:-(\d{2}))?", cleaned)
    if match is None:
        return None
    month = month_number(match.group(1))
    if month is None:
        return None
    if match.group(2) is not None:
        year = 2000 + int(match.group(2))
    elif period is not None:
        year = period.start.year
    else:
        return None
    start = date(year, month, 1)
    end = date(year, month, month_last_day(year, month))
    return start.isoformat(), end.isoformat()


def infer_year(month: int, period: Optional[Period]) -> Optional[int]:
    if period is None:
        return None
    if period.start.year == period.end.year:
        return period.start.year
    if month >= period.start.month:
        return period.start.year
    return period.end.year


def parse_single_partial_date(text: str, period: Optional[Period]) -> Optional[str]:
    parsed = parse_date(text)
    if parsed is not None:
        return parsed
    match = re.fullmatch(r"(\d{1,2})[\s-]+([A-Za-z]+)(?:[\s-]+(\d{2,4}))?", normalize_whitespace(text))
    if match is None:
        return None
    month = month_number(match.group(2))
    if month is None:
        return None
    year_text = match.group(3)
    if year_text is None:
        year = infer_year(month, period)
    elif len(year_text) == 2:
        year = 2000 + int(year_text)
    else:
        year = int(year_text)
    if year is None:
        return None
    return date(year, month, int(match.group(1))).isoformat()


def clean_date_range_text(value: str) -> str:
    text = normalize_whitespace(value)
    text = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)
    text = text.replace(" to ", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    return text


def parse_range_dates(value: Any, period: Optional[Period]) -> tuple[Optional[str], Optional[str]]:
    if isinstance(value, pd.Timestamp):
        iso = value.date().isoformat()
        return iso, iso
    if isinstance(value, datetime):
        iso = value.date().isoformat()
        return iso, iso
    if isinstance(value, date):
        iso = value.isoformat()
        return iso, iso
    text = clean_text(value)
    if text is None:
        return None, None
    cleaned = clean_date_range_text(text)

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})-(\d{1,2})/(\d{1,2})/(\d{2,4})", cleaned)
    if match is not None:
        start_year = int(match.group(3))
        end_year = int(match.group(6))
        if start_year < 100:
            start_year += 2000
        if end_year < 100:
            end_year += 2000
        return (
            date(start_year, int(match.group(2)), int(match.group(1))).isoformat(),
            date(end_year, int(match.group(5)), int(match.group(4))).isoformat(),
        )

    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]+)-(\d{2,4})-(\d{1,2})-([A-Za-z]+)-(\d{2,4})", cleaned, re.IGNORECASE)
    if match is not None:
        start_month = month_number(match.group(2))
        end_month = month_number(match.group(5))
        if start_month is None or end_month is None:
            return None, None
        start_year = int(match.group(3))
        end_year = int(match.group(6))
        if start_year < 100:
            start_year += 2000
        if end_year < 100:
            end_year += 2000
        return (
            date(start_year, start_month, int(match.group(1))).isoformat(),
            date(end_year, end_month, int(match.group(4))).isoformat(),
        )

    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]+)-(\d{1,2})-([A-Za-z]+)", cleaned, re.IGNORECASE)
    if match is not None:
        start_month = month_number(match.group(2))
        end_month = month_number(match.group(4))
        if start_month is None or end_month is None:
            return None, None
        start_year = infer_year(start_month, period)
        end_year = infer_year(end_month, period)
        if start_year is None or end_year is None:
            return None, None
        return (
            date(start_year, start_month, int(match.group(1))).isoformat(),
            date(end_year, end_month, int(match.group(3))).isoformat(),
        )

    match = re.fullmatch(r"(\d{1,2})-?(\d{1,2})\s*([A-Za-z]+)(?:\s+(\d{2,4}))?", cleaned, re.IGNORECASE)
    if match is not None:
        month = month_number(match.group(3))
        if month is None:
            return None, None
        year_text = match.group(4)
        if year_text is None:
            year = infer_year(month, period)
        elif len(year_text) == 2:
            year = 2000 + int(year_text)
        else:
            year = int(year_text)
        if year is None:
            return None, None
        return (
            date(year, month, int(match.group(1))).isoformat(),
            date(year, month, int(match.group(2))).isoformat(),
        )

    match = re.fullmatch(r"(\d{1,2})\s*([A-Za-z]+)-(\d{1,2})\s*([A-Za-z]+)(?:\s+(\d{2,4}))?", cleaned, re.IGNORECASE)
    if match is not None:
        start_month = month_number(match.group(2))
        end_month = month_number(match.group(4))
        if start_month is None or end_month is None:
            return None, None
        year_text = match.group(5)
        if year_text is None:
            start_year = infer_year(start_month, period)
            end_year = infer_year(end_month, period)
        elif len(year_text) == 2:
            start_year = 2000 + int(year_text)
            end_year = start_year
        else:
            start_year = int(year_text)
            end_year = start_year
        if start_year is None or end_year is None:
            return None, None
        return (
            date(start_year, start_month, int(match.group(1))).isoformat(),
            date(end_year, end_month, int(match.group(3))).isoformat(),
        )

    single = parse_single_partial_date(cleaned, period)
    if single is not None:
        return single, single
    return None, None


def only_meaningful_value(values: list[Any]) -> Optional[str]:
    meaningful = [clean_text(value) for value in values]
    meaningful = [value for value in meaningful if value is not None]
    if len(meaningful) != 1:
        return None
    return meaningful[0]


def is_repeated_header_row(values: list[Any]) -> bool:
    return score_header_row(values) >= HEADER_THRESHOLD


def is_minister_section_label(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in MINISTER_SECTION_KEYWORDS)


def extract_minister_name(text: str) -> Optional[str]:
    normalized = normalize_whitespace(
        text.replace("\x96", " - ").replace("–", " - ").replace("—", " - ")
    )
    if is_nil_value(normalized):
        return None
    if " - " in normalized:
        candidate = normalized.rsplit(" - ", 1)[1].strip(" ,")
        if candidate:
            return candidate
    if is_minister_section_label(normalized):
        return None
    return normalized


def canonical_records(source: TableSource) -> Iterator[dict[str, Any]]:
    field_map = detect_field_mapping(source.category, source.frame.columns)
    last_minister: Optional[str] = None
    pending_minister_name = False
    last_meeting_date: Any = None
    last_meeting_purpose: Any = None

    for index, row in source.frame.iterrows():
        row_values = row.tolist()
        single_value = only_meaningful_value(row_values)

        if single_value is not None and is_minister_section_label(single_value):
            minister_name = extract_minister_name(single_value)
            if minister_name is not None:
                last_minister = minister_name
                pending_minister_name = False
            else:
                pending_minister_name = True
            continue

        if pending_minister_name and single_value is not None:
            minister_name = extract_minister_name(single_value)
            if minister_name is not None:
                last_minister = minister_name
            pending_minister_name = False
            continue

        if is_repeated_header_row(row_values):
            continue

        record: dict[str, Any] = {
            "category": source.category,
            "record_index": index + 1,
            "source_url": source.source_url,
            "publication_url": source.publication.url,
            "publication_title": source.publication.title,
            "period": source.publication.period,
        }

        for field, column_name in field_map.items():
            if column_name in row.index:
                record[field] = row[column_name]

        minister = clean_text(record.get("minister"))
        if minister is not None:
            last_minister = minister
        elif last_minister is not None:
            record["minister"] = last_minister

        if source.category == "gifts" and clean_text(record.get("direction")) is None:
            direction = detect_gift_direction(source.title, source.file_name, source.source_url)
            if direction is None and field_map.get("counterparty") == "to":
                direction = "Given"
            if direction is None and field_map.get("counterparty") == "from":
                direction = "Received"
            if direction is not None:
                record["direction"] = direction

        if source.category == "meetings":
            counterparty = clean_text(record.get("counterparty"))
            if counterparty is not None and counterparty.startswith("-"):
                record["counterparty"] = counterparty.lstrip("- ")
                if clean_text(record.get("date")) is None and last_meeting_date is not None:
                    record["date"] = last_meeting_date
                if clean_text(record.get("purpose")) is None and last_meeting_purpose is not None:
                    record["purpose"] = last_meeting_purpose

            if clean_text(record.get("date")) is not None:
                last_meeting_date = record.get("date")
            if clean_text(record.get("purpose")) is not None:
                last_meeting_purpose = record.get("purpose")

        meaningful = [
            clean_text(value)
            for key, value in record.items()
            if key
            not in {
                "category",
                "record_index",
                "source_url",
                "publication_url",
                "publication_title",
                "period",
            }
        ]
        if not any(value is not None for value in meaningful):
            continue
        yield record
