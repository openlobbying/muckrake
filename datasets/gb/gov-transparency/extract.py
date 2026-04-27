import calendar
import importlib.util
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from .common import MONTH_NAMES, normalise_marker
    from .fingerprint import detect_header_row
    from .normalise import NormalisedSheet
    from .schema import Schema
    from .types import Provenance
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
    MONTH_NAMES = common_module.MONTH_NAMES
    normalise_marker = common_module.normalise_marker
    detect_header_row = common_module.load_sibling_module(__file__, __name__, "fingerprint").detect_header_row
    NormalisedSheet = common_module.load_sibling_module(__file__, __name__, "normalise").NormalisedSheet
    Schema = common_module.load_sibling_module(__file__, __name__, "schema").Schema
    Provenance = common_module.load_sibling_module(__file__, __name__, "types").Provenance


def extract(sheet: NormalisedSheet, schema: Schema, provenance: Provenance) -> list[dict]:
    if schema.sheet_type != "data":
        return []

    header_row = detect_header_row(sheet)
    data_start_row = header_row + schema.data_start_offset
    rows = sheet.rows[data_start_row:]
    results: list[dict] = []
    last_values: dict[int, str] = {}
    nil_markers = {normalise_marker(marker) for marker in schema.nil_return_markers}
    mapped_columns = list(schema.columns.values())

    for row_index, row in enumerate(rows, start=data_start_row):
        current = list(row)
        for column_index in schema.fill_down_columns:
            value = get_row_value(current, column_index).strip()
            if value == "":
                fill_value = last_values.get(column_index, "")
                ensure_row_width(current, column_index)
                current[column_index] = fill_value
            else:
                last_values[column_index] = value

        mapped_values = [get_row_value(current, column_index).strip() for column_index in mapped_columns]
        nil_check_values = list(mapped_values)
        if schema.date_source == "column":
            nil_check_values.append(get_row_value(current, schema.date_column).strip())
        if nil_markers and any(normalise_marker(value) in nil_markers for value in nil_check_values):
            continue
        if not any(mapped_values):
            continue
        if schema.date_source == "column" and get_row_value(current, schema.date_column).strip() == "":
            continue

        record = {
            canonical_name: get_row_value(current, column_index).strip()
            for canonical_name, column_index in schema.columns.items()
        }
        record.update(resolve_date(current, schema, provenance))
        record["row_index"] = row_index
        record["sheet_name"] = sheet.name
        results.append(record)

    return results


def resolve_date(row: list[str], schema: Schema, provenance: Provenance) -> dict:
    if schema.date_source == "none" or schema.date_precision == "quarter":
        if provenance.period_start is None or provenance.period_end is None:
            raise ValueError("Cannot resolve quarter date without provenance period")
        return {
            "date_from": provenance.period_start,
            "date_to": provenance.period_end,
            "date_precision": "quarter",
        }

    raw = get_row_value(row, schema.date_column).strip()
    if raw == "":
        raise ValueError("Cannot resolve blank date value")

    if schema.date_precision == "day":
        if schema.date_format is None:
            raise ValueError("Day-precision date schema requires date_format")
        normalized_raw = strip_day_ordinal(raw)
        try:
            parsed = datetime.strptime(normalized_raw, schema.date_format).date()
        except ValueError as exc:
            range_dates = parse_day_range(raw, provenance)
            if range_dates is not None:
                date_from, date_to = range_dates
                return {
                    "date_from": date_from,
                    "date_to": date_to,
                    "date_precision": "day",
                }
            raise ValueError(f"Cannot parse date {raw!r} with format {schema.date_format!r}") from exc
        return {"date": parsed, "date_precision": "day"}

    if schema.date_precision == "month":
        year_month = parse_month_value(raw, provenance)
        if year_month is None:
            raise ValueError(f"Unrecognised month value: {raw!r}")
        year, month = year_month
        return {
            "date_from": date(year, month, 1),
            "date_to": date(year, month, calendar.monthrange(year, month)[1]),
            "date_precision": "month",
        }

    raise ValueError(f"Unsupported date_precision: {schema.date_precision}")


def ensure_row_width(row: list[str], index: int) -> None:
    if index < len(row):
        return
    row.extend([""] * (index + 1 - len(row)))


def get_row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def strip_day_ordinal(value: str) -> str:
    return re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", value, flags=re.IGNORECASE)


def parse_month_value(raw: str, provenance: Provenance) -> tuple[int, int] | None:
    text = raw.strip()
    lowered = text.lower()
    if lowered in MONTH_NAMES:
        year = provenance.period_start.year if provenance.period_start is not None else None
        if year is None:
            raise ValueError(f"Cannot resolve month {raw!r} without provenance year")
        return year, MONTH_NAMES[lowered]

    month_year_match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", text)
    if month_year_match is not None:
        month = MONTH_NAMES.get(month_year_match.group(1).lower())
        if month is None:
            return None
        return int(month_year_match.group(2)), month

    short_match = re.fullmatch(r"([A-Za-z]{3,9})-(\d{2,4})", text)
    if short_match is not None:
        month = MONTH_NAMES.get(short_match.group(1).lower())
        if month is None:
            return None
        year = int(short_match.group(2))
        if year < 100:
            year += 2000 if year < 50 else 1900
        return year, month
    return None


def parse_day_range(raw: str, provenance: Provenance) -> tuple[date, date] | None:
    match = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)", strip_day_ordinal(raw).strip())
    if match is None:
        return None
    month = MONTH_NAMES.get(match.group(3).lower())
    if month is None or provenance.period_start is None:
        return None
    year = infer_year_from_month(month, provenance)
    start_day = int(match.group(1))
    end_day = int(match.group(2))
    return date(year, month, start_day), date(year, month, end_day)


def infer_year_from_month(month: int, provenance: Provenance) -> int:
    if provenance.period_start is None:
        raise ValueError("Cannot infer year without provenance period")
    if provenance.period_end is None or provenance.period_start.year == provenance.period_end.year:
        return provenance.period_start.year
    if month >= provenance.period_start.month:
        return provenance.period_start.year
    return provenance.period_end.year
