from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .normalise import NormalisedSheet as NormalisedSheetT

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

DISCLAIMER_PATTERNS = (
    r"^nil return\b",
    r"^none during this period\b",
    r"^return pending\b",
    r"^this return includes\b",
    r"^meetings were conducted\b",
    r"^retrospective trips\b",
)


@dataclass(frozen=True)
class HeaderMatch:
    row_index: int
    score: int


def detect_header_row(sheet: "NormalisedSheetT") -> int:
    if not sheet.rows:
        return 0

    best: HeaderMatch | None = None
    fallback_row: int | None = None

    for row_index, row in enumerate(sheet.rows):
        non_empty_cells = [cell for cell in row if cell.strip()]
        if not non_empty_cells:
            continue
        if fallback_row is None and looks_like_title_row(non_empty_cells):
            fallback_row = row_index
        score = score_header_candidate(sheet, row_index)
        if score is None:
            continue
        match = HeaderMatch(row_index=row_index, score=score)
        if best is None or match.score > best.score:
            best = match

    if best is not None:
        return best.row_index
    return fallback_row or 0


def fingerprint(sheet: "NormalisedSheetT") -> str:
    header_row = sheet.rows[detect_header_row(sheet)] if sheet.rows else []
    parts = [normalise_header_cell(cell) for cell in header_row if normalise_header_cell(cell)]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def header_signature(sheet: "NormalisedSheetT") -> list[str]:
    header_row = sheet.rows[detect_header_row(sheet)] if sheet.rows else []
    return [normalise_header_cell(cell) for cell in header_row if normalise_header_cell(cell)]


def score_header_candidate(sheet: "NormalisedSheetT", row_index: int) -> int | None:
    row = sheet.rows[row_index]
    non_empty_cells = [cell for cell in row if cell.strip()]
    if not non_empty_cells:
        return None
    if is_disclaimer_row(non_empty_cells):
        return None
    if is_uniform_row(non_empty_cells) and not looks_like_title_row(non_empty_cells) and not looks_like_header_row(non_empty_cells):
        return None

    score = 0
    label_like = sum(1 for value in non_empty_cells if looks_like_label(value))
    value_like = sum(1 for value in non_empty_cells if looks_like_pure_data(value))
    score += label_like * 4
    score -= value_like * 3
    score += len(non_empty_cells)
    if row_index <= 2:
        score += 6

    if looks_like_header_row(non_empty_cells):
        score += 8
    if looks_like_title_row(non_empty_cells):
        score -= 10

    next_rows = following_non_empty_rows(sheet.rows, row_index, limit=2)
    if next_rows:
        data_like_next_rows = sum(1 for candidate in next_rows if looks_like_data_row(candidate))
        score += data_like_next_rows * 4
        header_like_next_rows = sum(1 for candidate in next_rows if looks_like_header_row(candidate))
        score -= header_like_next_rows * 3

    if label_like == 0:
        return None
    return score


def following_non_empty_rows(rows: list[list[str]], row_index: int, limit: int) -> list[list[str]]:
    candidates: list[list[str]] = []
    for candidate in rows[row_index + 1 :]:
        non_empty_cells = [cell for cell in candidate if cell.strip()]
        if not non_empty_cells:
            continue
        candidates.append(non_empty_cells)
        if len(candidates) >= limit:
            break
    return candidates


def looks_like_data_row(values: list[str]) -> bool:
    if not values:
        return False
    value_like = sum(1 for value in values if looks_like_pure_data(value))
    label_like = sum(1 for value in values if looks_like_label(value))
    return value_like >= 1 or value_like >= label_like


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def normalise_header_cell(value: str) -> str:
    text = normalise_text(value)
    text = re.sub(r"\([^)]*£[^)]*\)", "", text)
    text = re.sub(r"\([^)]*\)", lambda m: "" if len(m.group(0)) <= 6 else m.group(0), text)
    text = re.sub(r"[*`]+", "", text)
    text = re.sub(r"[:;,.]+", "", text)
    text = text.replace("organisation", "organization")
    text = text.replace("organisations", "organizations")
    text = text.replace("adviser", "advisor")
    text = text.replace("advisers", "advisors")
    text = text.replace("outside employment", "outside_employment")
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def is_disclaimer_row(values: list[str]) -> bool:
    if len(values) > 2:
        return False
    for value in values:
        text = normalise_text(value)
        if any(re.search(pattern, text) for pattern in DISCLAIMER_PATTERNS):
            return True
    return False


def looks_like_label(value: str) -> bool:
    text = normalise_header_cell(value)
    if not text:
        return False
    if looks_like_pure_data(text):
        return False
    if re.search(
        r"\b(name|names|date|dates|period|purpose|purposes|meeting|meetings|gift|gifts|given|received|hospitality|travel|travels|organization|organizations|minister|ministers|advisor|advisors|value|values|outcome|outcomes|destination|destinations|cost|costs|media|role|roles|employment|outside_employment|official|officials|person|people|guest|guests|from|to|from/to|type|transport|accompanied|spouse|family|friend|start|end)\b",
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
    return re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned) is not None


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
