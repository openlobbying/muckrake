import calendar
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from .common import MONTH_NAMES, normalise_marker
    from .fingerprint import detect_header_row
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
    MONTH_NAMES = common_module.MONTH_NAMES
    normalise_marker = common_module.normalise_marker
    detect_header_row = common_module.load_sibling_module(__file__, __name__, "fingerprint").detect_header_row
    NormalisedSheet = common_module.load_sibling_module(__file__, __name__, "normalise").NormalisedSheet

SCHEMAS_DIR = Path(__file__).with_name("schemas")


@dataclass(frozen=True)
class Schema:
    fingerprint: str
    sheet_type: str
    activity_type: str | None = None
    data_start_offset: int = 1
    fill_down_columns: list[int] = field(default_factory=list)
    nil_return_markers: list[str] = field(default_factory=list)
    date_source: str = "none"
    date_column: int | None = None
    date_format: str | None = None
    date_precision: str = "quarter"
    columns: dict[str, int] = field(default_factory=dict)

    @property
    def data_start_row(self) -> int:
        raise AttributeError("data_start_row depends on the sheet header row")


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
    columns = data.get("columns", {})
    if not isinstance(columns, dict):
        raise ValueError("Schema 'columns' must be an object")
    return Schema(
        fingerprint=require_string(data, "fingerprint"),
        sheet_type=require_string(data, "sheet_type"),
        activity_type=optional_string(data, "activity_type"),
        data_start_offset=require_int(data, "data_start_offset", default=1),
        fill_down_columns=require_int_list(data, "fill_down_columns"),
        nil_return_markers=require_string_list(data, "nil_return_markers"),
        date_source=require_string(data, "date_source", default="none"),
        date_column=optional_int(data, "date_column"),
        date_format=optional_string(data, "date_format"),
        date_precision=require_string(data, "date_precision", default="quarter"),
        columns={key: require_mapping_int(columns, key) for key in columns},
    )


def validate_schema(schema: Schema, sheet: NormalisedSheet) -> None:
    header_row = detect_header_row(sheet)
    max_columns = max((len(row) for row in sheet.rows), default=0)

    for name, index in schema.columns.items():
        if index < 0 or index >= max_columns:
            raise ValueError(f"Schema column {name!r} points outside sheet width: {index}")

    data_start_row = header_row + schema.data_start_offset
    if data_start_row >= len(sheet.rows):
        raise ValueError(
            f"Schema data_start_offset {schema.data_start_offset} exceeds sheet rows for {sheet.name!r}"
        )

    if schema.sheet_type == "data" and "minister_name" not in schema.columns:
        raise ValueError("Data schemas must define a minister_name column")

    mapped_columns = list(schema.columns.values())
    if schema.sheet_type == "data" and not has_non_nil_data_row(sheet, schema, data_start_row, mapped_columns):
        raise ValueError(f"Schema {schema.fingerprint} has no non-nil data rows in sheet {sheet.name!r}")

    if schema.date_source == "column":
        if schema.date_column is None:
            raise ValueError("Schema with date_source='column' must define date_column")
        if schema.date_column < 0 or schema.date_column >= max_columns:
            raise ValueError(f"Schema date_column points outside sheet width: {schema.date_column}")
        validate_date_column(schema, sheet, data_start_row)


def has_non_nil_data_row(
    sheet: NormalisedSheet,
    schema: Schema,
    data_start_row: int,
    mapped_columns: list[int],
) -> bool:
    nil_markers = {normalise_marker(marker) for marker in schema.nil_return_markers}
    for row in sheet.rows[data_start_row:]:
        values = [get_row_value(row, index).strip() for index in mapped_columns]
        if not any(values):
            continue
        if nil_markers and any(normalise_marker(value) in nil_markers for value in values):
            continue
        return True
    return False


def validate_date_column(schema: Schema, sheet: NormalisedSheet, data_start_row: int) -> None:
    for row in sheet.rows[data_start_row:]:
        raw = get_row_value(row, schema.date_column).strip()
        if not raw:
            continue
        if normalise_marker(raw) in {normalise_marker(marker) for marker in schema.nil_return_markers}:
            continue
        parse_date_value(raw, schema)
        return
    raise ValueError(f"Schema {schema.fingerprint} has no parseable date values in sheet {sheet.name!r}")


def parse_date_value(raw: str, schema: Schema) -> date | tuple[int, int] | tuple[date, date]:
    if schema.date_precision == "day":
        if schema.date_format is None:
            raise ValueError("Day-precision date schemas must define date_format")
        return datetime.strptime(raw, schema.date_format).date()
    if schema.date_precision == "month":
        month = MONTH_NAMES.get(raw.strip().lower())
        if month is None:
            raise ValueError(f"Unrecognised month value: {raw!r}")
        return 1900, month
    if schema.date_precision == "quarter":
        return date(1900, 1, 1), date(1900, 3, calendar.monthrange(1900, 3)[1])
    raise ValueError(f"Unsupported date_precision: {schema.date_precision}")


def get_row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


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


def require_mapping_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Schema column {key!r} must be an integer")
    return value
