from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .normalise import NormalisedSheet as NormalisedSheetT
    from .schema import Schema as SchemaT

try:
    from .common import normalise_marker, should_skip_row
    from .fingerprint import detect_header_row
    from .normalise import NormalisedSheet
    from .schema import Schema
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


@dataclass(frozen=True)
class RowOutcome:
    row_index: int
    values: list[str]
    mapped: dict[str, str]
    header_row_index: int


@dataclass(frozen=True)
class RowStats:
    total_rows: int = 0
    mapped_rows: int = 0
    skip_prefix_rows: int = 0
    nil_rows: int = 0
    blank_rows: int = 0
    blank_date_rows: int = 0
    blank_end_date_rows: int = 0


_ROW_EVAL_CACHE: dict[tuple[tuple[tuple[str, ...], ...], tuple], tuple[list[RowOutcome], RowStats]] = {}


def evaluate_rows(sheet: "NormalisedSheetT", schema: "SchemaT") -> tuple[list[RowOutcome], RowStats]:
    schema_key = (
        schema.fingerprint,
        schema.layout.data_start_offset,
        tuple(schema.layout.fill_down_columns),
        tuple(schema.layout.skip_row_prefixes),
        tuple(schema.layout.nil_return_markers),
        schema.date.mode,
        schema.date.column,
        schema.date.end_column,
        tuple((rule.type, rule.format, rule.precision) for rule in schema.date.parsers),
        tuple(sorted(schema.mapping.items())),
    )
    cache_key = (tuple(tuple(row) for row in sheet.rows), schema_key)
    cached = _ROW_EVAL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    header_row_index = detect_header_row(sheet)
    data_start_row = header_row_index + schema.layout.data_start_offset
    rows = sheet.rows[data_start_row:]
    last_values: dict[int, str] = {}
    nil_markers = {normalise_marker(marker) for marker in schema.layout.nil_return_markers}
    mapped_columns = list(schema.mapping.values())
    outcomes: list[RowOutcome] = []
    stats = RowStats(total_rows=len(rows))

    for row_index, row in enumerate(rows, start=data_start_row):
        current = list(row)
        if should_skip_row(current, schema.layout.skip_row_prefixes):
            stats = replace_stats(stats, skip_prefix_rows=stats.skip_prefix_rows + 1)
            continue

        for column_index in schema.layout.fill_down_columns:
            value = get_row_value(current, column_index).strip()
            if value == "":
                fill_value = last_values.get(column_index, "")
                ensure_row_width(current, column_index)
                current[column_index] = fill_value
            else:
                last_values[column_index] = value

        mapped_values = [get_row_value(current, column_index).strip() for column_index in mapped_columns]
        nil_check_values = list(mapped_values)
        if schema.date.mode in {"column", "column_range"}:
            nil_check_values.append(get_row_value(current, schema.date.column).strip())
            if schema.date.end_column is not None:
                nil_check_values.append(get_row_value(current, schema.date.end_column).strip())

        if row_index == header_row_index and any(mapped_values):
            continue

        if any(mapped_values):
            stats = replace_stats(stats, mapped_rows=stats.mapped_rows + 1)

        if nil_markers and any(normalise_marker(value) in nil_markers for value in nil_check_values if value):
            stats = replace_stats(stats, nil_rows=stats.nil_rows + 1)
            continue

        if not any(mapped_values):
            stats = replace_stats(stats, blank_rows=stats.blank_rows + 1)
            continue

        if schema.date.mode in {"column", "column_range"} and get_row_value(current, schema.date.column).strip() == "":
            stats = replace_stats(stats, blank_date_rows=stats.blank_date_rows + 1)
            continue

        if schema.date.end_column is not None and get_row_value(current, schema.date.end_column).strip() == "":
            stats = replace_stats(stats, blank_end_date_rows=stats.blank_end_date_rows + 1)
            continue

        mapped = {
            canonical_name: get_row_value(current, column_index).strip()
            for canonical_name, column_index in schema.mapping.items()
        }
        outcomes.append(
            RowOutcome(
                row_index=row_index,
                values=current,
                mapped=mapped,
                header_row_index=header_row_index,
            )
        )

    result = (outcomes, stats)
    _ROW_EVAL_CACHE[cache_key] = result
    return result


def replace_stats(stats: RowStats, **updates) -> RowStats:
    return RowStats(
        total_rows=updates.get("total_rows", stats.total_rows),
        mapped_rows=updates.get("mapped_rows", stats.mapped_rows),
        skip_prefix_rows=updates.get("skip_prefix_rows", stats.skip_prefix_rows),
        nil_rows=updates.get("nil_rows", stats.nil_rows),
        blank_rows=updates.get("blank_rows", stats.blank_rows),
        blank_date_rows=updates.get("blank_date_rows", stats.blank_date_rows),
        blank_end_date_rows=updates.get("blank_end_date_rows", stats.blank_end_date_rows),
    )


def ensure_row_width(row: list[str], index: int) -> None:
    if index < len(row):
        return
    row.extend([""] * (index + 1 - len(row)))


def get_row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]
