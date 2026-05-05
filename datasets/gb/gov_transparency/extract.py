from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .normalise import NormalisedSheet as NormalisedSheetT
    from .schema import Schema as SchemaT
    from .types import Provenance as ProvenanceT

try:
    from .date_rules import resolve_date
    from .normalise import NormalisedSheet
    from .rows import evaluate_rows
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
    resolve_date = common_module.load_sibling_module(__file__, __name__, "date_rules").resolve_date
    NormalisedSheet = common_module.load_sibling_module(__file__, __name__, "normalise").NormalisedSheet
    evaluate_rows = common_module.load_sibling_module(__file__, __name__, "rows").evaluate_rows
    Schema = common_module.load_sibling_module(__file__, __name__, "schema").Schema
    Provenance = common_module.load_sibling_module(__file__, __name__, "types").Provenance


def extract(sheet: "NormalisedSheetT", schema: "SchemaT", provenance: "ProvenanceT") -> list[dict[str, str | int]]:
    if schema.sheet_type != "data":
        return []

    row_outcomes, _stats = evaluate_rows(sheet, schema)
    results: list[dict[str, str | int]] = []
    for row_outcome in row_outcomes:
        record: dict[str, str | int] = dict(row_outcome.mapped)
        if schema.subject.source != "column":
            record["official_name"] = resolve_subject_name(schema, provenance, sheet)
        record.update(resolve_date(row_outcome.values, schema, provenance.period_start, provenance.period_end))
        record["row_index"] = row_outcome.row_index
        record["sheet_name"] = sheet.name
        results.append(record)
    return results


def resolve_subject_name(schema: "SchemaT", provenance: "ProvenanceT", sheet: "NormalisedSheetT") -> str:
    if schema.subject.source == "value":
        if schema.subject.value is None:
            raise ValueError("Schema subject.source='value' requires a value")
        return schema.subject.value
    if schema.subject.source == "sheet_name":
        candidate = sheet.name.strip()
        if not candidate:
            raise ValueError("Could not derive official_name from sheet name")
        return candidate
    if schema.subject.source == "provenance":
        candidate = (provenance.attachment_title or provenance.publication_title).strip()
        lowered = candidate.lower()
        cut_markers = [
            " guests at chequers",
            " chequers",
            " ministerial gifts hospitality travel and meetings",
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
            raise ValueError("Could not derive official_name from provenance")
        return candidate
    raise ValueError(f"Unsupported subject source: {schema.subject.source}")
