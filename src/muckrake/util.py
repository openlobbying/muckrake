from typing import Optional, Any

from muckrake.utils.dates import parse_date, parse_date_token


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
