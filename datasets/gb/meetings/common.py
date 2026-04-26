import csv
import hashlib
import logging
import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Optional
from urllib.parse import urlparse

import pandas as pd

from muckrake.dataset import Dataset
from muckrake.util import parse_amount, to_string
from muckrake.utils.dates import (
    month_last_day,
    parse_date,
    parse_month_span as shared_parse_month_span,
    parse_month_value as shared_parse_month_value,
    parse_partial_date as shared_parse_partial_date,
    parse_year_hint_date as shared_parse_year_hint_date,
    safe_iso_date,
)

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .validation import MeetingsValidation

TABULAR_EXTENSIONS = {"csv", "xlsx", "xls"}
HEADER_THRESHOLD = 3
CATEGORY_TRAILING_WINDOW = 40

CATEGORY_KEYWORDS = {
    "meetings": ("meeting",),
    "hospitality": ("hospitality",),
    "gifts": ("gift",),
    "travel": ("travel",),
}

OUT_OF_SCOPE_ATTACHMENT_KEYWORDS = (
    "official visit",
    "official visits",
    "uk visits",
    "official reception",
    "official receptions",
    "charity reception",
    "charity receptions",
    "official and charity receptions",
    "chequers",
    "chevening",
)

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
    "septeber": 9,
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
            "ministers",
            "prime minister",
            "minister name",
            "ministerial name",
            "name of minister",
            "official",
        ],
        "date": ["date", "date of meeting", "dates of meeting", "meeting date"],
        "counterparty": [
            "name of organisation or individual",
            "name of individual or organisation",
            "name of individual s",
            "name of individual",
            "name of individuals",
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
        "minister": ["minister", "ministers", "prime minister"],
        "date": ["date", "date gift given", "date gift received", "date received", "date given"],
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
        "minister": ["minister", "ministers", "prime minister"],
        "date": ["date", "date of hospitality"],
        "counterparty": [
            "person or organisation that offered hospitality",
            "individual or organisation that offered hospitality",
            "name of organisation",
            "name of organization",
        ],
        "kind": [
            "type of hospitality received",
            "type of hospitality given",
            "type of hospitality received include an asterisk against the entry if accompanied by spouse partner or other family member or friend",
        ],
        "guest": [
            "accompanied by spouse family members or friend",
            "accompanied by guest",
        ],
    },
    "travel": {
        "minister": ["minister", "ministers", "prime minister"],
        "start_date": ["start date", "start date of trip"],
        "end_date": ["end date", "end date of trip"],
        "date_text": ["dates of trip", "date(s) of trip", "date of trip", "date"],
        "destination": ["destination"],
        "purpose": ["purpose of trip", "purpose"],
        "transport": [
            "mode of transport",
            "modes of transport",
            "no 32 the royal squadron or other raf or charter or eurostar",
            "no.32 the royal squadron or other raf or charter or scheduled or eurostar",
            "scheduled no.32 the royal squadron or other raf or charter or scheduled or eurostar",
            "scheduled no 32 the royal squadron or other raf or charter or scheduled or eurostar",
        ],
        "transport_cost": [
            "cost of private jet or raf plane hire if relevant gbp",
            "subtotal of all travel costs including any non scheduled raf flights gbp",
            "subtotal of all travel costs including any non scheduled raf flights",
            "subtotal of all travel costs including any non-scheduled raf flights",
        ],
        "accompanying_officials": [
            "number of officials who accompanied minister if non shceduled travel was used",
            "number of officials who accompanied minister if non scheduled travel was used",
            "number of officials who accompanied the minister if non scheduled flight was taken",
            "number of officials who accompanied the minister if non-scheduled flight was taken",
            "number of officials accompanying minister where non scheduled travel is used",
            "number of officials accompanying ministers where non scheduled travel is used",
            "number of officials accompanying ministers where non-scheduled travel is used",
        ],
        "guest": [
            "accompanied by spouse family members or friend at public expense",
            "accompanied by spouse partner at public expense",
        ],
        "associated_cost": [
            "subtotal of associated costs for minister only including all visas accommodation meals etc gbp",
            "subtotal of associated costs for minister only including all visas accommodation meals etc.",
            "subtotal of associated costs for minister only including all visas accommodation meals etc",
        ],
        "total_cost": [
            "total cost for minister only including all visas accommodation travel meals etc gbp",
            "total cost gbp",
            "total cost",
            "total cost including travel and accommodation of minister only",
            "total cost for minister only including all visas accommodation travel meals etc",
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
RECORD_METADATA_FIELDS = {
    "category",
    "record_index",
    "source_url",
    "publication_url",
    "publication_title",
    "period",
}


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


def make_resource_name(publication: Publication, file_name: str, max_stem_length: int = 120) -> str:
    publication_stem = Path(urlparse(publication.url).path).name or "publication"
    source_stem = Path(file_name).stem or "attachment"
    suffix = Path(file_name).suffix
    digest = hashlib.sha1(f"{publication.url}|{file_name}".encode("utf-8")).hexdigest()[:12]

    stem = normalize_column_name(f"{publication_stem} {source_stem}").replace(" ", "-")
    stem = stem.strip("-") or "resource"
    stem = stem[:max_stem_length].rstrip("-") or "resource"
    return f"{stem}-{digest}{suffix}"


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


def parse_period(title: str) -> Optional[Period]:
    text = normalize_whitespace(re.sub(r"[-_]+", " ", title))
    match = re.search(
        r"(?P<start_day>\d{1,2})?\s*(?P<start_month>[A-Za-z]+)(?:\s+(?P<start_year>\d{4}))?\s+to\s+(?P<end_day>\d{1,2})?\s*(?P<end_month>[A-Za-z]+)\s+(?P<end_year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if match is not None:
        start_month = month_number(match.group("start_month"))
        end_month = month_number(match.group("end_month"))
        if start_month is None or end_month is None:
            return None
        end_year = int(match.group("end_year"))
        start_year_text = match.group("start_year")
        if start_year_text is not None:
            start_year = int(start_year_text)
        elif start_month > end_month:
            start_year = end_year - 1
        else:
            start_year = end_year
        start_day = min(int(match.group("start_day") or 1), month_last_day(start_year, start_month))
        end_day = min(
            int(match.group("end_day") or month_last_day(end_year, end_month)),
            month_last_day(end_year, end_month),
        )
        return Period(
            start=date(start_year, start_month, start_day),
            end=date(end_year, end_month, end_day),
        )

    match = re.search(
        r"(?P<start_month>[A-Za-z]+)(?:\s+to)?\s+(?P<end_month>[A-Za-z]+)\s+(?P<year>\d{4})",
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


def extract_publications(
    dataset: Dataset,
    collection_urls: str | Iterable[str],
    validator: "MeetingsValidation | None" = None,
    department_name: str | None = None,
) -> list[Publication]:
    publications: list[Publication] = []
    seen_urls: set[str] = set()
    for collection_url in iter_collection_urls(collection_urls):
        try:
            doc = dataset.fetch_html(collection_url, cache_days=30, absolute_links=True)
        except Exception as exc:
            if validator is not None and department_name is not None:
                validator.log_collection_page_error(department_name, collection_url, exc)
            else:
                log.warning("Skipping unreadable collection page %s: %s", collection_url, exc)
            continue
        for element in doc.xpath("//a[starts-with(@href, 'https://www.gov.uk/government/publications/')]"):
            url = element.get("href")
            if url is None or url in seen_urls:
                continue
            seen_urls.add(url)
            title = normalize_whitespace("".join(element.itertext()))
            url_title = Path(urlparse(url).path).name.replace("-", " ")
            period = parse_period(title) or parse_period(url_title)
            publications.append(Publication(url=url, title=title, period=period))
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


def is_out_of_scope_attachment(*parts: str) -> bool:
    text = " ".join(normalize_whitespace(part).lower() for part in parts if part)
    return any(keyword in text for keyword in OUT_OF_SCOPE_ATTACHMENT_KEYWORDS)


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


def category_score(category: str, columns: Any) -> int:
    return len(detect_field_mapping(category, columns))


def detect_category_from_columns(columns: Any) -> Optional[str]:
    scores = {
        category: category_score(category, columns)
        for category in FIELD_ALIASES
    }
    best_score = max(scores.values(), default=0)
    if best_score == 0:
        return None
    best_categories = [category for category, score in scores.items() if score == best_score]
    if len(best_categories) != 1:
        return None
    return best_categories[0]


def resolve_table_category(columns: Any, *parts: str) -> Optional[str]:
    metadata_category = detect_category(*parts)
    column_category = detect_category_from_columns(columns)
    if column_category is None:
        return metadata_category
    if metadata_category is None:
        return column_category
    if category_score(column_category, columns) > category_score(metadata_category, columns):
        return column_category
    return metadata_category


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


def extract_stacked_minister(values: list[Any]) -> Optional[str]:
    for value in reversed(values):
        text = to_string(value)
        if text is None:
            continue
        lowered = text.lower()
        if "minister" not in lowered:
            continue
        if "," in text:
            candidate = text.rsplit(",", 1)[-1].strip()
            if candidate:
                return candidate
        return text
    return None


def normalize_stacked_single_column_frame(frame: pd.DataFrame) -> Optional[pd.DataFrame]:
    normalized = frame.copy()
    normalized = normalized.dropna(axis=1, how="all")
    normalized = normalized.dropna(axis=0, how="all")
    if normalized.empty or len(normalized.columns) != 1:
        return None

    values = normalized.iloc[:, 0].tolist()
    normalized_values = [
        normalize_column_name(text)
        if (text := to_string(value)) is not None
        else None
        for value in values
    ]

    for index in range(len(normalized_values) - 2):
        header_values = normalized_values[index : index + 3]
        if header_values != ["date of meeting", "name of individual s", "purpose of meeting"]:
            continue

        data_values = [to_string(value) for value in values[index + 3 :]]
        data_values = [value for value in data_values if value is not None]
        rows = [data_values[offset : offset + 3] for offset in range(0, len(data_values), 3)]
        rows = [row for row in rows if len(row) == 3]
        if not rows:
            return None

        table = pd.DataFrame(rows, columns=["date of meeting", "name of individual s", "purpose of meeting"], dtype=object)
        minister = extract_stacked_minister(values[:index])
        if minister is not None:
            table.insert(0, "minister", minister)
        return normalize_frame(table)

    return None


def normalize_tabular_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized = normalized.dropna(axis=1, how="all")
    normalized = normalized.dropna(axis=0, how="all")
    if normalized.empty:
        return normalized
    stacked = normalize_stacked_single_column_frame(normalized)
    if stacked is not None:
        return stacked
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
    path = dataset.fetch_resource(make_resource_name(publication, file_name), source_url)
    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            frame = pd.read_csv(path, encoding=encoding, header=None, dtype=object)
            return normalize_tabular_frame(frame)
        except Exception as exc:
            last_error = exc
            try:
                with path.open("r", encoding=encoding, newline="") as fh:
                    rows = list(csv.reader(fh))
                if rows:
                    header_width = len(rows[0])
                    padded = []
                    for row in rows:
                        trimmed = row[:header_width]
                        padded.append(trimmed + [None] * (header_width - len(trimmed)))
                    frame = pd.DataFrame(padded, dtype=object)
                    return normalize_tabular_frame(frame)
            except Exception:
                pass
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def is_probably_text_file(path: Path, chunk_size: int = 2048) -> bool:
    with path.open("rb") as fh:
        chunk = fh.read(chunk_size)
    if not chunk:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def read_excel_tables(
    dataset: Dataset, publication: Publication, file_name: str, source_url: str
) -> Iterator[tuple[str, pd.DataFrame]]:
    path = dataset.fetch_resource(make_resource_name(publication, file_name), source_url)
    if is_probably_text_file(path):
        yield file_name, read_csv_table(dataset, publication, file_name, source_url)
        return

    engine = "openpyxl" if file_name.lower().endswith("xlsx") else "xlrd"
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Unknown extension is not supported and will be removed",
            category=UserWarning,
            module=r"openpyxl\.worksheet\._reader",
        )
        with pd.ExcelFile(path, engine=engine) as workbook:
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
    dataset: Dataset,
    collection_urls: str | Iterable[str],
    validator: "MeetingsValidation | None" = None,
    department_name: str | None = None,
) -> Iterator[TableSource]:
    for publication in extract_publications(
        dataset,
        collection_urls,
        validator=validator,
        department_name=department_name,
    ):
        try:
            doc = dataset.fetch_html(publication.url, cache_days=30, absolute_links=True)
        except Exception as exc:
            if validator is not None and department_name is not None:
                validator.log_publication_page_error(department_name, publication.url, exc)
            else:
                log.warning("Skipping unreadable publication page %s: %s", publication.url, exc)
            continue
        attachment_links: dict[str, str] = {}
        for element in doc.xpath("//a[contains(@href, 'assets.publishing.service.gov.uk')]"):
            source_url = element.get("href")
            if source_url is None:
                continue
            title = normalize_whitespace("".join(element.itertext()))
            best_title = attachment_links.get(source_url)
            if best_title is None or (not best_title and title):
                attachment_links[source_url] = title

        for source_url, title in attachment_links.items():
            ext = extension_for_url(source_url)
            if ext not in TABULAR_EXTENSIONS:
                continue
            file_name = Path(urlparse(source_url).path).name
            if is_out_of_scope_attachment(title, file_name, source_url):
                if validator is not None and department_name is not None:
                    validator.log_out_of_scope_table(
                        department_name,
                        publication.url,
                        source_url,
                        file_name,
                        title=title,
                    )
                continue
            if ext == "csv":
                try:
                    frame = read_csv_table(dataset, publication, file_name, source_url)
                except Exception as exc:
                    if validator is not None and department_name is not None:
                        validator.log_attachment_read_error(
                            department_name,
                            publication.url,
                            source_url,
                            file_name,
                            exc,
                        )
                    else:
                        log.warning("Skipping unreadable CSV attachment %s: %s", source_url, exc)
                    continue
                if frame.empty:
                    if validator is not None and department_name is not None:
                        validator.log_empty_table(
                            department_name,
                            publication.url,
                            source_url,
                            file_name,
                            title=title,
                        )
                    continue
                category = resolve_table_category(frame.columns, title, file_name, source_url)
                if category is None:
                    if validator is not None and department_name is not None:
                        validator.log_unknown_category(
                            department_name,
                            publication.url,
                            source_url,
                            file_name,
                            title=title,
                        )
                    continue
                yield TableSource(publication, category, source_url, title or file_name, file_name, frame)
                continue
            try:
                tables = read_excel_tables(dataset, publication, file_name, source_url)
                for sheet_name, frame in tables:
                    if is_out_of_scope_attachment(sheet_name, title, file_name, source_url):
                        if validator is not None and department_name is not None:
                            validator.log_out_of_scope_table(
                                department_name,
                                publication.url,
                                source_url,
                                file_name,
                                title=title,
                                sheet_name=sheet_name,
                            )
                        continue
                    category = resolve_table_category(frame.columns, sheet_name, title, file_name, source_url)
                    if category is None:
                        if validator is not None and department_name is not None:
                            validator.log_unknown_category(
                                department_name,
                                publication.url,
                                source_url,
                                file_name,
                                title=title,
                                sheet_name=sheet_name,
                            )
                        continue
                    yield TableSource(publication, category, source_url, sheet_name, file_name, frame)
            except Exception as exc:
                if validator is not None and department_name is not None:
                    validator.log_attachment_read_error(
                        department_name,
                        publication.url,
                        source_url,
                        file_name,
                        exc,
                    )
                else:
                    log.warning("Skipping unreadable spreadsheet attachment %s: %s", source_url, exc)
                continue


def period_bounds(period: Optional[Period]) -> tuple[Optional[date], Optional[date]]:
    if period is None:
        return None, None
    return period.start, period.end


def parse_cell_date(value: Any) -> Optional[str]:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return parse_date(value)


def parse_month_value(value: str, period: Optional[Period]) -> Optional[tuple[str, str]]:
    start, end = period_bounds(period)
    return shared_parse_month_value(value, start, end)


def infer_year(month: int, period: Optional[Period]) -> Optional[int]:
    start, end = period_bounds(period)
    if start is None or end is None:
        return None
    if start.year == end.year:
        return start.year
    if month >= start.month:
        return start.year
    return end.year


def parse_partial_date(text: str, period: Optional[Period]) -> Optional[str]:
    start, end = period_bounds(period)
    return shared_parse_partial_date(text, start, end)


def parse_year_hint_date(text: str, period: Optional[Period]) -> Optional[str]:
    start, end = period_bounds(period)
    return shared_parse_year_hint_date(text, start, end)


def parse_month_span(text: str, period: Optional[Period]) -> Optional[tuple[str, str]]:
    if period is None:
        return None
    return shared_parse_month_span(text, period.end.year)


def date_within_period(parsed: str, period: Optional[Period]) -> bool:
    if period is None or len(parsed) != 10:
        return True
    try:
        parsed_date = date.fromisoformat(parsed)
    except ValueError:
        return True
    return period.start.year <= parsed_date.year <= period.end.year


def source_period(source: TableSource) -> Optional[Period]:
    for part in (
        source.publication.title,
        source.publication.url,
        source.title,
        source.file_name,
        source.source_url,
    ):
        if not part:
            continue
        period = parse_period(part)
        if period is not None:
            return period

    year_hint: Optional[int] = None
    for part in (source.publication.title, source.publication.url, source.source_url):
        if not part:
            continue
        years = {int(match) for match in re.findall(r"\b(?:19|20)\d{2}\b", part)}
        if len(years) == 1:
            year_hint = years.pop()
            break

    if year_hint is None:
        return None

    for part in (source.title, source.file_name, source.source_url):
        month_span = shared_parse_month_span(part, year_hint)
        if month_span is None:
            continue
        start_date, end_date = month_span
        return Period(start=date.fromisoformat(start_date), end=date.fromisoformat(end_date))

    return None


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
            safe_iso_date(start_year, int(match.group(2)), int(match.group(1))),
            safe_iso_date(end_year, int(match.group(5)), int(match.group(4))),
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
            safe_iso_date(start_year, start_month, int(match.group(1))),
            safe_iso_date(end_year, end_month, int(match.group(4))),
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
            safe_iso_date(start_year, start_month, int(match.group(1))),
            safe_iso_date(end_year, end_month, int(match.group(3))),
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
            safe_iso_date(year, month, int(match.group(1))),
            safe_iso_date(year, month, int(match.group(2))),
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
            safe_iso_date(start_year, start_month, int(match.group(1))),
            safe_iso_date(end_year, end_month, int(match.group(3))),
        )

    single = parse_partial_date(cleaned, period)
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
    period = source_period(source)
    base_record = {
        "category": source.category,
        "source_url": source.source_url,
        "publication_url": source.publication.url,
        "publication_title": source.publication.title,
        "period": period,
    }
    default_gift_direction = None
    if source.category == "gifts":
        default_gift_direction = detect_gift_direction(source.title, source.file_name, source.source_url)
        if default_gift_direction is None and field_map.get("counterparty") == "to":
            default_gift_direction = "Given"
        if default_gift_direction is None and field_map.get("counterparty") == "from":
            default_gift_direction = "Received"

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

        record: dict[str, Any] = dict(base_record, record_index=index + 1)

        for field, column_name in field_map.items():
            if column_name in row.index:
                record[field] = row[column_name]

        minister = clean_text(record.get("minister"))
        if minister is not None:
            last_minister = minister
        elif last_minister is not None:
            record["minister"] = last_minister

        if source.category == "gifts" and clean_text(record.get("direction")) is None:
            if default_gift_direction is not None:
                record["direction"] = default_gift_direction

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
            if key not in RECORD_METADATA_FIELDS
        ]
        if not any(value is not None for value in meaningful):
            continue
        yield record
