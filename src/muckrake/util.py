from calendar import monthrange
from datetime import date, datetime
from typing import Optional, Any


DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%B %d, %Y", "%Y/%m/%d"]


def to_string(value: Any) -> Optional[str]:
    """Clean a string value, handling NaN and None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "n/a"):
        return None
    return text


def parse_amount(text: Any) -> Optional[float]:
    """Parse a currency amount string into a float."""
    text = to_string(text)
    if text is None:
        return None

    # Remove common currency symbols and commas
    cleaned = text.replace("£", "").replace("$", "").replace("€", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(text: Any, format: Optional[str] = None) -> Optional[str]:
    """Parse a date string into ISO format (YYYY-MM-DD)."""
    text = to_string(text)
    if not text:
        return None

    if "T" in text:
        text = text.split("T")[0]

    formats = list(DATE_FORMATS)
    if format:
        formats.insert(0, format)

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

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
