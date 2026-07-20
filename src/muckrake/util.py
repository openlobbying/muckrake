from typing import Any

# Re-exported for consumers that import date helpers from muckrake.util.
from muckrake.utils.dates import parse_date, parse_date_token  # noqa: F401


def to_string(value: Any) -> str | None:
    """Clean a string value, handling NaN and None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "n/a"):
        return None
    return text


def parse_amount(text: Any) -> float | None:
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
