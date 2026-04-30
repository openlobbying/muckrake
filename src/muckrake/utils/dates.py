from calendar import monthrange
from datetime import date, datetime, timedelta
import math
import re
from typing import Any, Optional


DATE_FORMATS = [
    "%d/%m/%Y",
    "%d/%m/%y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b %Y",
    "%d %b %y",
    "%d %B %Y",
    "%d %B %y",
    "%B %d, %Y",
    "%A, %B %d, %Y",
    "%A, %d %B %Y",
    "%A, %d %B %y",
    "%Y/%m/%d",
]

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "februrary": 2,
    "mar": 3,
    "march": 3,
    "marc": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "junee": 6,
    "july": 7,
    "jul": 7,
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


def to_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "n/a"):
        return None
    return text


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def month_number(value: str) -> Optional[int]:
    return MONTHS.get(value.strip().lower())


def month_last_day(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def safe_iso_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalize_date_text(value: Any) -> Optional[str]:
    text = to_string(value)
    if text is None:
        return None
    text = normalize_whitespace(text)
    text = text.lstrip(" ?")
    text = text.rstrip("*`")
    text = text.replace("–", "-").replace("—", "-").replace("Ð", "-").replace("�", "-")
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-\s*", "-", text)
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", text):
        text = text.replace(".", "/")
    elif re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{2,4}", text):
        text = text.replace(".", "/")
    elif re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", text):
        text = text.replace(".", "-")
    elif re.fullmatch(r"\d{2}/\d{2}\d{4}", text):
        text = f"{text[:2]}/{text[3:5]}/{text[5:]}"
    elif re.fullmatch(r"\d{4}\s+\d{1,2}\s+\d{1,2}", text):
        text = re.sub(r"\s+", "-", text)
    elif re.fullmatch(r"\d{4}-\d{1,2}\s+\d{1,2}", text):
        text = text.replace(" ", "-")
    elif re.fullmatch(r"\d{4}\s+\d{1,2}-\d{1,2}", text):
        text = text.replace(" ", "-")
    return text


def infer_year(month: int, start: Optional[date], end: Optional[date]) -> Optional[int]:
    if start is None or end is None:
        return None
    if start.year == end.year:
        return start.year
    if month >= start.month:
        return start.year
    return end.year


def parse_date(text: Any, format: Optional[str] = None) -> Optional[str]:
    """Parse a date string into ISO format (YYYY-MM-DD)."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        if isinstance(text, float) and math.isnan(text):
            return None
        serial = int(text)
        if 10000 <= serial <= 100000:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()

    text = normalize_date_text(text)
    if not text:
        return None

    if re.fullmatch(r"\d{5}", text):
        serial = int(text)
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()

    if len(text) >= 11 and text[4] == "-" and text[7] == "-" and text[10] == "T":
        text = text.split("T")[0]

    formats = list(DATE_FORMATS)
    if format:
        formats.insert(0, format)

    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).date()
            return parsed.isoformat()
        except (ValueError, TypeError):
            continue

    return None


def parse_month_value(value: Any, start: Optional[date] = None, end: Optional[date] = None) -> Optional[tuple[str, str]]:
    text = normalize_date_text(value)
    if text is None:
        return None
    if len(text) >= 11 and text[4] == "-" and text[7] == "-" and text[10] == "T":
        text = text.split("T", 1)[0]
    day_match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if day_match is not None:
        year = int(day_match.group(1))
        month = int(day_match.group(2))
        if 1 <= month <= 12:
            return (
                date(year, month, 1).isoformat(),
                date(year, month, month_last_day(year, month)).isoformat(),
            )
        return None
    iso_match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if iso_match is not None:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        if 1 <= month <= 12:
            return (
                date(year, month, 1).isoformat(),
                date(year, month, month_last_day(year, month)).isoformat(),
            )
        return None
    match = re.fullmatch(r"([A-Za-z]+)(?:[\s,-]+(\d{2,4}))?", text)
    if match is None:
        return None
    month = month_number(match.group(1))
    if month is None:
        return None
    if match.group(2) is not None:
        year = int(match.group(2))
        if year < 100:
            year += 2000
    else:
        year = infer_year(month, start, end)
    if year is None:
        return None
    return (
        date(year, month, 1).isoformat(),
        date(year, month, month_last_day(year, month)).isoformat(),
    )


def parse_day_range(value: Any, start: Optional[date] = None, end: Optional[date] = None) -> Optional[tuple[str, str]]:
    text = normalize_date_text(value)
    if text is None:
        return None
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})-(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if match is not None:
        start_year = int(match.group(3))
        end_year = int(match.group(6))
        if start_year < 100:
            start_year += 2000
        if end_year < 100:
            end_year += 2000
        start_date = safe_iso_date(start_year, int(match.group(2)), int(match.group(1)))
        end_date = safe_iso_date(end_year, int(match.group(5)), int(match.group(4)))
        if start_date is None or end_date is None:
            return None
        return start_date, end_date
    match = re.fullmatch(r"(\d{4})[/-](\d{1,2})-(\d{1,2})\D+(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match is not None:
        start_date = safe_iso_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        end_date = safe_iso_date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
        if start_date is None or end_date is None:
            return None
        return start_date, end_date
    match = re.fullmatch(r"(\d{1,2})(?:-|\s+to\s+)(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{2,4}))?", text)
    if match is not None:
        month = month_number(match.group(3))
        if month is None:
            return None
        year_text = match.group(4)
        if year_text is None:
            year = infer_year(month, start, end)
        elif len(year_text) == 2:
            year = 2000 + int(year_text)
        else:
            year = int(year_text)
        if year is None:
            return None
        start_date = safe_iso_date(year, month, int(match.group(1)))
        end_date = safe_iso_date(year, month, int(match.group(2)))
        if start_date is None or end_date is None:
            return None
        return start_date, end_date

    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})-(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})", text)
    if match is not None:
        start_month = month_number(match.group(2))
        end_month = month_number(match.group(5))
        if start_month is None or end_month is None:
            return None
        start_year = int(match.group(3))
        end_year = int(match.group(6))
        if start_year < 100:
            start_year += 2000
        if end_year < 100:
            end_year += 2000
        start_date = safe_iso_date(start_year, start_month, int(match.group(1)))
        end_date = safe_iso_date(end_year, end_month, int(match.group(4)))
        if start_date is None or end_date is None:
            return None
        return start_date, end_date

    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)(?:-|\s+to\s+)(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{2,4}))?", text)
    if match is None:
        return None
    start_month = month_number(match.group(2))
    end_month = month_number(match.group(4))
    if start_month is None or end_month is None:
        return None
    year_text = match.group(5)
    if year_text is None:
        end_year = infer_year(end_month, start, end)
    elif len(year_text) == 2:
        end_year = 2000 + int(year_text)
    else:
        end_year = int(year_text)
    if end_year is None:
        return None
    start_year = end_year - 1 if start_month > end_month else end_year
    start_date = safe_iso_date(start_year, start_month, int(match.group(1)))
    end_date = safe_iso_date(end_year, end_month, int(match.group(3)))
    if start_date is None or end_date is None:
        return None
    return start_date, end_date


def parse_day_value(
    value: Any,
    start: Optional[date] = None,
    end: Optional[date] = None,
    format: Optional[str] = None,
) -> Optional[str | tuple[str, str]]:
    parsed = parse_date(value, format)
    if parsed is not None:
        return parsed
    parsed = parse_partial_date(value, start, end)
    if parsed is not None:
        return parsed
    parsed = parse_year_hint_date(value, start, end)
    if parsed is not None:
        return parsed
    return parse_day_range(value, start, end)


def parse_day_or_month_value(
    value: Any,
    start: Optional[date] = None,
    end: Optional[date] = None,
    format: Optional[str] = None,
) -> Optional[tuple[str, str | tuple[str, str]]]:
    parsed_day = parse_day_value(value, start, end, format)
    if parsed_day is not None:
        return "day", parsed_day
    parsed_month = parse_month_value(value, start, end)
    if parsed_month is not None:
        return "month", parsed_month
    return None


def parse_partial_date(value: Any, start: Optional[date] = None, end: Optional[date] = None) -> Optional[str]:
    text = normalize_date_text(value)
    if text is None:
        return None
    parsed = parse_date(text)
    if parsed is not None:
        return parsed
    match = re.fullmatch(r"(\d{1,2})[\s/-]+([A-Za-z]+)(?:[\s,-]+(\d{2,4}))?", text)
    if match is None:
        return None
    month = month_number(match.group(2))
    if month is None:
        return None
    year_text = match.group(3)
    if year_text is None:
        year = infer_year(month, start, end)
    elif len(year_text) == 2:
        year = 2000 + int(year_text)
    else:
        year = int(year_text)
    if year is None:
        return None
    return safe_iso_date(year, month, int(match.group(1)))


def parse_month_span(value: Any, year_hint: Optional[int] = None) -> Optional[tuple[str, str]]:
    text = normalize_date_text(value)
    if text is None or year_hint is None:
        return None
    month_matches = [month_number(token) for token in re.findall(r"[A-Za-z]+", text)]
    months = [month for month in month_matches if month is not None]
    if len(months) < 2:
        return None
    start_month = months[0]
    end_month = months[-1]
    start_year = year_hint - 1 if start_month > end_month else year_hint
    return (
        date(start_year, start_month, 1).isoformat(),
        date(year_hint, end_month, month_last_day(year_hint, end_month)).isoformat(),
    )


def parse_year_hint_date(value: Any, start: Optional[date] = None, end: Optional[date] = None) -> Optional[str]:
    if start is None or end is None:
        return None
    text = normalize_date_text(value)
    if text is None:
        return None

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match is not None:
        raw_year = int(match.group(3))
        candidates = [raw_year]
        if raw_year >= 1000:
            candidates.append(raw_year - 1000)
        for candidate_year in candidates:
            if start.year <= candidate_year <= end.year:
                parsed = safe_iso_date(candidate_year, int(match.group(2)), int(match.group(1)))
                if parsed is not None:
                    return parsed

    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match is None:
        return None
    year = int(match.group(1))
    if 1900 <= year <= 2100:
        return None
    candidate_years = [int(match.group(1)[::-1])]
    if year >= 1000:
        candidate_years.append(year - 1000)
    for candidate_year in candidate_years:
        if start.year <= candidate_year <= end.year:
            parsed = safe_iso_date(candidate_year, int(match.group(2)), int(match.group(3)))
            if parsed is not None:
                return parsed
    return None


def parse_date_token(value: Optional[str], is_end: bool = False) -> Optional[date]:
    if value is None:
        return None
    if len(value) == 7:
        year, month = value.split("-")
        day = monthrange(int(year), int(month))[1] if is_end else 1
        return date.fromisoformat(f"{value}-{day:02d}")
    if len(value) == 10:
        return date.fromisoformat(value)
    return None
