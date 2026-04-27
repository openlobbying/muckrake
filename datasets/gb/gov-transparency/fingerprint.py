import hashlib
import importlib.util
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from .normalise import NormalisedSheet
except ImportError:
    common_spec = importlib.util.spec_from_file_location(
        f"{__name__}.common",
        Path(__file__).with_name("common.py"),
    )
    if common_spec is None or common_spec.loader is None:
        raise RuntimeError("Could not load gov-transparency common module")
    common_module = importlib.util.module_from_spec(common_spec)
    sys.modules[common_spec.name] = common_module
    common_spec.loader.exec_module(common_module)
    NormalisedSheet = common_module.load_sibling_module(__file__, __name__, "normalise").NormalisedSheet

MONTH_NAMES = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}

DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%B %Y",
    "%b %Y",
)


def detect_header_row(sheet: NormalisedSheet) -> int:
    if not sheet.rows:
        return 0

    # The first sufficiently populated row with more label-like than value-like
    # cells is stable enough to identify a recurring sheet template.
    fallback_row: int | None = None
    for row_index, row in enumerate(sheet.rows):
        if not row:
            continue
        non_empty_cells = [cell for cell in row if cell.strip()]
        if not non_empty_cells:
            continue
        if fallback_row is None and looks_like_title_row(non_empty_cells):
            fallback_row = row_index
        if len(non_empty_cells) * 2 < len(row):
            continue
        if is_uniform_row(non_empty_cells) and not looks_like_title_row(non_empty_cells):
            continue
        if looks_like_header_row(non_empty_cells):
            return row_index
        value_like_cells = sum(1 for cell in row if looks_like_pure_data(cell))
        if value_like_cells * 2 < len(row):
            return row_index
    return fallback_row or 0


def fingerprint(sheet: NormalisedSheet) -> str:
    header_row = sheet.rows[detect_header_row(sheet)] if sheet.rows else []
    parts = [normalise_text(sheet.name), *[normalise_text(cell) for cell in header_row]]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def is_uniform_row(values: list[str]) -> bool:
    if not values:
        return False
    normalised = {normalise_text(value) for value in values}
    return len(normalised) == 1


def looks_like_header_row(values: list[str]) -> bool:
    label_like = sum(1 for value in values if looks_like_label(value))
    return label_like * 2 >= len(values)


def looks_like_title_row(values: list[str]) -> bool:
    if len(values) != 1:
        return False
    return looks_like_label(values[0])


def looks_like_label(value: str) -> bool:
    text = normalise_text(value)
    if not text:
        return False
    if looks_like_pure_data(text):
        return False
    if re.search(
        r"\b(name|names|date|dates|purpose|purposes|meeting|meetings|gift|gifts|hospitality|travel|travels|organisation|organisations|organization|organizations|minister|ministers|adviser|advisers|advisor|advisors|value|values|outcome|outcomes|destination|destinations|cost|costs|media|role|roles|employment|official|officials|person|people)\b",
        text,
    ):
        return True
    return False


def looks_like_pure_data(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if looks_like_number(text):
        return True
    if looks_like_date(text):
        return True
    return False


def looks_like_number(value: str) -> bool:
    cleaned = value.replace(",", "").replace("£", "").replace("$", "").replace("%", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned):
        return True
    return False


def looks_like_date(value: str) -> bool:
    lowered = normalise_text(value)
    if lowered in MONTH_NAMES:
        return True
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", value):
        return True
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        return True
    if re.fullmatch(r"[A-Za-z]{3,9}-\d{2,4}", value):
        return True
    for date_format in DATE_FORMATS:
        try:
            datetime.strptime(value, date_format)
            return True
        except ValueError:
            continue
    return False
