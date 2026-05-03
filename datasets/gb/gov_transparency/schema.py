from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .normalise import NormalisedSheet as NormalisedSheetT

try:
    from .common import load_sibling_module
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
    load_sibling_module = common_module.load_sibling_module
    NormalisedSheet = common_module.load_sibling_module(__file__, __name__, "normalise").NormalisedSheet

SCHEMAS_DIR = Path(__file__).with_name("schemas")
DEFAULT_NIL_RETURN_MARKERS = [
    "Nil Return",
    "Nil return",
    "Nil Return ",
    "NIL",
    "NIL RETURN",
    "NIL Return",
    "Nil return all other ministers",
    "None in this period",
]
VALID_SHEET_TYPES = {"data", "notes", "ignore"}
VALID_ACTIVITY_TYPES = {"meetings", "gifts", "hospitality", "travel", "outside_employment"}
VALID_SUBJECT_SOURCES = {"column", "value", "provenance"}
VALID_DATE_MODES = {"none", "provenance_period", "column", "column_range"}
VALID_ROLE_MODES = {"default", "hosted_by_official"}
VALID_MAPPING_KEYS = {
    "official_name",
    "counterparty_name",
    "summary",
    "amount",
    "outcome_text",
    "location",
}
VALID_DATE_RULE_TYPES = {
    "strptime",
    "excel_serial",
    "iso_datetime",
    "day_range",
    "month_name",
    "month_name_from_period",
}

_RESOLVE_DATE = None
_EVALUATE_ROWS = None


@dataclass(frozen=True)
class SubjectConfig:
    source: str = "column"
    value: str | None = None


@dataclass(frozen=True)
class LayoutConfig:
    data_start_offset: int = 1
    fill_down_columns: list[int] = field(default_factory=list)
    skip_row_prefixes: list[str] = field(default_factory=list)
    nil_return_markers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DateRule:
    type: str
    format: str | None = None
    precision: str | None = None


@dataclass(frozen=True)
class DateConfig:
    mode: str = "none"
    column: int | None = None
    end_column: int | None = None
    parsers: list[DateRule] = field(default_factory=list)


@dataclass(frozen=True)
class Schema:
    fingerprint: str
    sheet_type: str
    reason: str | None = None
    activity_type: str | None = None
    subject: SubjectConfig = field(default_factory=SubjectConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    date: DateConfig = field(default_factory=DateConfig)
    mapping: dict[str, int] = field(default_factory=dict)
    role_mode: str = "default"


def load_schema(fingerprint: str) -> Schema | None:
    path = SCHEMAS_DIR / f"{fingerprint}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return schema_from_dict(data)


def schema_from_dict(data: dict[str, Any]) -> Schema:
    if not isinstance(data, dict):
        raise ValueError("Schema file must contain a JSON object")

    allowed_keys = {"fingerprint", "sheet_type", "reason", "activity_type", "subject", "layout", "date", "mapping", "role_mode"}
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown schema fields: {', '.join(unknown_keys)}")

    fingerprint = require_string(data, "fingerprint")
    sheet_type = require_string(data, "sheet_type")
    if sheet_type not in VALID_SHEET_TYPES:
        raise ValueError(f"Unsupported sheet_type: {sheet_type}")

    reason = optional_string(data, "reason")
    activity_type = optional_string(data, "activity_type")
    if sheet_type == "data":
        if activity_type is None:
            raise ValueError("Data schemas must define activity_type")
        if activity_type not in VALID_ACTIVITY_TYPES:
            raise ValueError(f"Unsupported activity_type: {activity_type}")
        if reason is not None:
            raise ValueError("Only notes and ignore schemas may define reason")
    else:
        if activity_type is not None:
            raise ValueError("Only data schemas may define activity_type")
        if reason is None or not reason.strip():
            raise ValueError("Notes and ignore schemas must define a non-empty reason")

    subject = subject_from_dict(data.get("subject", {}))
    layout = layout_from_dict(data.get("layout", {}), sheet_type)
    date = date_from_dict(data.get("date", {}))
    mapping = mapping_from_dict(data.get("mapping", {}), sheet_type, subject)
    role_mode = require_string(data, "role_mode", default="default")
    if role_mode not in VALID_ROLE_MODES:
        raise ValueError(f"Unsupported role_mode: {role_mode}")

    if sheet_type != "data" and role_mode != "default":
        raise ValueError("Only data schemas may define a non-default role_mode")

    if date.mode in {"column", "column_range"} and date.column is None:
        raise ValueError("Column-based date modes require a date column")
    if date.mode == "column_range" and date.end_column is None:
        raise ValueError("column_range date mode requires an end_column")
    if date.mode == "provenance_period" and date.parsers:
        raise ValueError("provenance_period date mode must not define parser rules")
    if date.mode in {"column", "column_range"} and not date.parsers:
        raise ValueError("Column-based date modes must define parser rules")
    if date.mode == "none" and date.parsers:
        raise ValueError("date.mode='none' must not define parser rules")

    return Schema(
        fingerprint=fingerprint,
        sheet_type=sheet_type,
        reason=reason,
        activity_type=activity_type,
        subject=subject,
        layout=layout,
        date=date,
        mapping=mapping,
        role_mode=role_mode,
    )


def validate_schema(schema: Schema, sheet: "NormalisedSheetT") -> None:
    resolve_date, evaluate_rows = load_validation_helpers()

    max_columns = max((len(row) for row in sheet.rows), default=0)
    for name, index in schema.mapping.items():
        if index < 0 or index >= max_columns:
            raise ValueError(f"Schema column {name!r} points outside sheet width: {index}")

    if schema.date.column is not None and (schema.date.column < 0 or schema.date.column >= max_columns):
        raise ValueError(f"Schema date column points outside sheet width: {schema.date.column}")
    if schema.date.end_column is not None and (schema.date.end_column < 0 or schema.date.end_column >= max_columns):
        raise ValueError(f"Schema end date column points outside sheet width: {schema.date.end_column}")

    if schema.sheet_type != "data":
        return

    rows, stats = evaluate_rows(sheet, schema)
    if schema.date.mode == "column_range" and stats.blank_end_date_rows > 0:
        raise ValueError(f"Schema {schema.fingerprint} has blank end date values in sheet {sheet.name!r}")
    if not rows:
        if stats.mapped_rows == 0 and stats.skip_prefix_rows == 0:
            raise ValueError(f"Schema {schema.fingerprint} has no data rows in sheet {sheet.name!r}")
        return

    if schema.date.mode == "provenance_period":
        return

    has_date = False
    for row in rows:
        resolved = resolve_date(row.values, schema, period_start=date(1900, 1, 1), period_end=date(1900, 12, 31))
        if resolved:
            has_date = True
    if schema.date.mode != "none" and not has_date:
        raise ValueError(f"Schema {schema.fingerprint} has no parseable date values in sheet {sheet.name!r}")


def load_validation_helpers():
    global _RESOLVE_DATE, _EVALUATE_ROWS
    if _RESOLVE_DATE is None:
        _RESOLVE_DATE = load_sibling_module(__file__, __name__, "date_rules").resolve_date
    if _EVALUATE_ROWS is None:
        _EVALUATE_ROWS = load_sibling_module(__file__, __name__, "rows").evaluate_rows
    return _RESOLVE_DATE, _EVALUATE_ROWS


def subject_from_dict(data: Any) -> SubjectConfig:
    if not isinstance(data, dict):
        raise ValueError("Schema 'subject' must be an object")
    allowed_keys = {"source", "value"}
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown subject fields: {', '.join(unknown_keys)}")
    source = require_string(data, "source", default="column")
    if source not in VALID_SUBJECT_SOURCES:
        raise ValueError(f"Unsupported subject source: {source}")
    value = optional_string(data, "value")
    if source == "value" and (value is None or not value.strip()):
        raise ValueError("Subject source 'value' requires a non-empty value")
    if source != "value" and value is not None:
        raise ValueError("Subject value is only allowed when source='value'")
    return SubjectConfig(source=source, value=value)


def layout_from_dict(data: Any, sheet_type: str) -> LayoutConfig:
    if not isinstance(data, dict):
        raise ValueError("Schema 'layout' must be an object")
    allowed_keys = {"data_start_offset", "fill_down_columns", "skip_row_prefixes", "nil_return_markers"}
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown layout fields: {', '.join(unknown_keys)}")
    if sheet_type != "data" and any(key in data for key in ("data_start_offset", "fill_down_columns", "skip_row_prefixes", "nil_return_markers")):
        if data:
            raise ValueError("Only data schemas may define layout settings")
    nil_markers = require_string_list(data, "nil_return_markers")
    if sheet_type == "data":
        nil_markers = merge_nil_return_markers(nil_markers)
    return LayoutConfig(
        data_start_offset=require_int(data, "data_start_offset", default=1),
        fill_down_columns=require_int_list(data, "fill_down_columns"),
        skip_row_prefixes=require_string_list(data, "skip_row_prefixes"),
        nil_return_markers=nil_markers,
    )


def date_from_dict(data: Any) -> DateConfig:
    if not isinstance(data, dict):
        raise ValueError("Schema 'date' must be an object")
    allowed_keys = {"mode", "column", "end_column", "parsers"}
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown date fields: {', '.join(unknown_keys)}")
    mode = require_string(data, "mode", default="none")
    if mode not in VALID_DATE_MODES:
        raise ValueError(f"Unsupported date mode: {mode}")
    parsers = [date_rule_from_dict(item) for item in require_object_list(data, "parsers")]
    return DateConfig(
        mode=mode,
        column=optional_int(data, "column"),
        end_column=optional_int(data, "end_column"),
        parsers=parsers,
    )


def date_rule_from_dict(data: Any) -> DateRule:
    if not isinstance(data, dict):
        raise ValueError("Date parser rules must be objects")
    allowed_keys = {"type", "format", "precision"}
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown date rule fields: {', '.join(unknown_keys)}")
    rule_type = require_string(data, "type")
    if rule_type not in VALID_DATE_RULE_TYPES:
        raise ValueError(f"Unsupported date rule type: {rule_type}")
    precision = optional_string(data, "precision")
    if precision is not None and precision not in {"day", "month"}:
        raise ValueError(f"Unsupported date rule precision: {precision}")
    rule_format = optional_string(data, "format")
    if rule_type == "strptime" and rule_format is None:
        raise ValueError("strptime date rules require a format")
    return DateRule(type=rule_type, format=rule_format, precision=precision)


def mapping_from_dict(data: Any, sheet_type: str, subject: SubjectConfig) -> dict[str, int]:
    if not isinstance(data, dict):
        raise ValueError("Schema 'mapping' must be an object")
    unknown_keys = sorted(set(data) - VALID_MAPPING_KEYS)
    if unknown_keys:
        raise ValueError(f"Unsupported mapping keys: {', '.join(unknown_keys)}")
    if sheet_type != "data" and data:
        raise ValueError("Only data schemas may define mapped columns")
    if sheet_type == "data" and subject.source == "column" and "official_name" not in data:
        raise ValueError("Data schemas with subject.source='column' must define an official_name column")
    if subject.source != "column" and "official_name" in data:
        raise ValueError("official_name must not be mapped when subject.source is not 'column'")
    return {key: require_mapping_int(data, key) for key in data}


def merge_nil_return_markers(markers: list[str]) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for marker in [*DEFAULT_NIL_RETURN_MARKERS, *markers]:
        normalised = marker.strip().casefold()
        if normalised in seen:
            continue
        seen.add(normalised)
        combined.append(marker)
    return combined


def require_string(data: dict[str, Any], key: str, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Schema field {key!r} must be a string")
    return value


def optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Schema field {key!r} must be a string or null")
    return value


def require_int(data: dict[str, Any], key: str, default: int | None = None) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"Schema field {key!r} must be an integer")
    return value


def optional_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"Schema field {key!r} must be an integer or null")
    return value


def require_int_list(data: dict[str, Any], key: str) -> list[int]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
        raise ValueError(f"Schema field {key!r} must be a list of integers")
    return value


def require_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Schema field {key!r} must be a list of strings")
    return value


def require_object_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Schema field {key!r} must be a list of objects")
    return value


def require_mapping_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Schema mapping {key!r} must be an integer")
    return value
