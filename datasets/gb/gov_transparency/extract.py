import importlib.util
import sys
from datetime import date
from pathlib import Path
import re

from muckrake.utils.dates import parse_day_or_month_value, parse_day_value, parse_month_value

try:
    from .common import normalise_marker, should_skip_row
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
    normalise_marker = common_module.normalise_marker
    should_skip_row = common_module.should_skip_row
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
        if should_skip_row(current, schema.skip_row_prefixes):
            continue
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
            if schema.end_date_column is not None:
                nil_check_values.append(get_row_value(current, schema.end_date_column).strip())
        if nil_markers and any(normalise_marker(value) in nil_markers for value in nil_check_values):
            continue
        if not any(mapped_values):
            continue
        if schema.date_source == "column" and get_row_value(current, schema.date_column).strip() == "":
            continue
        if schema.end_date_column is not None and get_row_value(current, schema.end_date_column).strip() == "":
            continue

        record = {
            canonical_name: get_row_value(current, column_index).strip()
            for canonical_name, column_index in schema.columns.items()
        }
        if schema.subject_name_source != "column":
            record["subject_name"] = resolve_subject_name(schema, provenance)
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
            "start_date": provenance.period_start.isoformat(),
            "end_date": provenance.period_end.isoformat(),
            "date_precision": "quarter",
        }

    raw = get_row_value(row, schema.date_column).strip()
    if raw == "":
        raise ValueError("Cannot resolve blank date value")

    if schema.end_date_column is not None:
        end_raw = get_row_value(row, schema.end_date_column).strip()
        if end_raw == "":
            raise ValueError("Cannot resolve blank end date value")
        start_parsed = parse_day_value(raw, provenance.period_start, provenance.period_end, schema.date_format)
        end_parsed = parse_day_value(end_raw, provenance.period_start, provenance.period_end, schema.date_format)
        if not isinstance(start_parsed, str) or not isinstance(end_parsed, str):
            raise ValueError(f"Cannot parse date range {raw!r} to {end_raw!r} with format {schema.date_format!r}")
        if start_parsed == end_parsed:
            return {"date": start_parsed, "date_precision": "day"}
        return {
            "start_date": start_parsed,
            "end_date": end_parsed,
            "date_precision": "day",
        }

    if schema.date_precision == "day":
        parsed = parse_day_value(raw, provenance.period_start, provenance.period_end, schema.date_format)
        if parsed is not None:
            return resolve_day_result(parsed)
        raise ValueError(f"Cannot parse date {raw!r} with format {schema.date_format!r}")

    if schema.date_precision == "day_or_month":
        parsed = parse_day_or_month_value(raw, provenance.period_start, provenance.period_end, schema.date_format)
        if parsed is None:
            raise ValueError(f"Cannot parse mixed day/month date {raw!r} with format {schema.date_format!r}")
        precision, value = parsed
        if precision == "day":
            return resolve_day_result(value)
        return {
            "date": value[0][:7],
            "date_precision": "month",
        }

    if schema.date_precision == "month":
        parsed = parse_month_value(raw, provenance.period_start, provenance.period_end)
        if parsed is None:
            raise ValueError(f"Unrecognised month value: {raw!r}")
        return {
            "date": parsed[0][:7],
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


def resolve_day_result(parsed: str | tuple[str, str]) -> dict:
    if isinstance(parsed, tuple):
        return {
            "start_date": parsed[0],
            "end_date": parsed[1],
            "date_precision": "day",
        }
    return {"date": parsed, "date_precision": "day"}


def resolve_subject_name(schema: Schema, provenance: Provenance) -> str:
    if schema.subject_name_source == "value":
        if schema.subject_name_value is None:
            raise ValueError("Schema subject_name_source='value' requires subject_name_value")
        return schema.subject_name_value
    if schema.subject_name_source == "provenance":
        candidate = (provenance.attachment_title or provenance.publication_title).strip()
        lowered = candidate.lower()
        cut_markers = [
            " guests at chequers",
            " chequers",
            " ministerial gifts, hospitality, travel and meetings",
            " ministerial gifts",
            " ministerial hospitality",
            " ministerial meetings",
            " ministerial overseas travel",
        ]
        for marker in cut_markers:
            index = lowered.find(marker)
            if index != -1:
                candidate = candidate[:index]
                break
        candidate = re.sub(r"[_,-]+", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,")
        if not candidate:
            raise ValueError("Could not derive subject_name from provenance")
        return candidate
    raise ValueError(f"Unsupported subject_name_source: {schema.subject_name_source}")
