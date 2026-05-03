from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from muckrake.utils.dates import parse_date, parse_day_range, parse_month_value, parse_partial_date, parse_year_hint_date

if TYPE_CHECKING:
    from .schema import DateRule as DateRuleT, Schema as SchemaT

try:
    from .schema import DateRule, Schema
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
    schema_module = common_module.load_sibling_module(__file__, __name__, "schema")
    DateRule = schema_module.DateRule
    Schema = schema_module.Schema


def resolve_date(
    row: list[str],
    schema: "SchemaT",
    period_start: date | None,
    period_end: date | None,
) -> dict[str, str]:
    if schema.date.mode == "none":
        return {}
    if schema.date.mode == "provenance_period":
        if period_start is None or period_end is None:
            raise ValueError("Cannot resolve provenance_period date without publication period")
        return {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "date_precision": "quarter",
        }

    raw = get_row_value(row, schema.date.column).strip()
    if raw == "":
        raise ValueError("Cannot resolve blank date value")

    if schema.date.mode == "column_range":
        end_raw = get_row_value(row, schema.date.end_column).strip()
        if end_raw == "":
            raise ValueError("Cannot resolve blank end date value")
        start_parsed = parse_value(raw, schema.date.parsers, period_start, period_end)
        end_parsed = parse_value(end_raw, schema.date.parsers, period_start, period_end)
        if start_parsed is None or end_parsed is None:
            raise ValueError(f"Cannot parse date range {raw!r} to {end_raw!r}")
        if start_parsed["precision"] != "day" or end_parsed["precision"] != "day":
            raise ValueError("Explicit date ranges must resolve to day precision")
        if start_parsed["kind"] == "range" or end_parsed["kind"] == "range":
            raise ValueError("Explicit start/end columns must not themselves resolve to ranges")
        if start_parsed["value"] == end_parsed["value"]:
            return {"date": start_parsed["value"], "date_precision": "day"}
        return {
            "start_date": start_parsed["value"],
            "end_date": end_parsed["value"],
            "date_precision": "day",
        }

    parsed = parse_value(raw, schema.date.parsers, period_start, period_end)
    if parsed is None:
        raise ValueError(f"Cannot parse date value {raw!r}")

    if parsed["kind"] == "day":
        return {"date": parsed["value"], "date_precision": "day"}
    if parsed["kind"] == "month":
        return {"date": parsed["value"], "date_precision": "month"}
    if parsed["kind"] == "range":
        return {
            "start_date": parsed["start"],
            "end_date": parsed["end"],
            "date_precision": "day",
        }
    raise ValueError(f"Unsupported parsed date kind: {parsed['kind']}")


def parse_value(
    raw: str,
    rules: list["DateRuleT"],
    period_start: date | None,
    period_end: date | None,
) -> dict[str, str] | None:
    for rule in rules:
        parsed = parse_with_rule(raw, rule, period_start, period_end)
        if parsed is not None:
            return parsed
    return None


def parse_with_rule(
    raw: str,
    rule: "DateRuleT",
    period_start: date | None,
    period_end: date | None,
) -> dict[str, str] | None:
    if rule.type == "strptime":
        parsed = parse_date(raw, rule.format)
        if parsed is None:
            return None
        return coerce_parsed_date(parsed, rule.precision)

    if rule.type == "excel_serial":
        normalized = raw.strip()
        if re.fullmatch(r"\d+\.0", normalized):
            normalized = normalized[:-2]
        parsed = parse_date(normalized)
        if parsed is None:
            return None
        return coerce_parsed_date(parsed, rule.precision)

    if rule.type == "iso_datetime":
        parsed = parse_date(raw)
        if parsed is None:
            parsed = parse_partial_date(raw, period_start, period_end)
        if parsed is None:
            parsed = parse_year_hint_date(raw, period_start, period_end)
        if parsed is None:
            return None
        return coerce_parsed_date(parsed, rule.precision)

    if rule.type == "day_range":
        parsed = parse_day_range(raw, period_start, period_end)
        if parsed is None:
            return None
        return {"kind": "range", "start": parsed[0], "end": parsed[1], "precision": "day"}

    if rule.type == "month_name":
        parsed = parse_month_value(raw, period_start, period_end)
        if parsed is None:
            return None
        return {"kind": "month", "value": parsed[0][:7], "precision": "month"}

    if rule.type == "month_name_from_period":
        parsed = parse_month_value(raw, period_start, period_end)
        if parsed is None:
            return None
        return {"kind": "month", "value": parsed[0][:7], "precision": "month"}

    raise ValueError(f"Unsupported date rule type: {rule.type}")


def coerce_parsed_date(parsed: str, precision: str | None) -> dict[str, str]:
    if precision == "month":
        return {"kind": "month", "value": parsed[:7], "precision": "month"}
    return {"kind": "day", "value": parsed, "precision": "day"}


def get_row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]
