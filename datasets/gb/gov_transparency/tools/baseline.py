from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from org_id import make_hashed_id

if TYPE_CHECKING:
    from ..types import Provenance as ProvenanceT

try:
    from ..common import load_sibling_module, parse_period
    from ..entities import emit_entities
    from ..extract import extract
    from ..fingerprint import fingerprint
    from ..normalise import normalise
    from ..schema import SCHEMAS_DIR, load_schema, schema_from_dict, validate_schema
    from ..types import Provenance
except ImportError:
    common_spec = importlib.util.spec_from_file_location(
        f"{__name__}.common",
        Path(__file__).resolve().parents[1] / "common.py",
    )
    if common_spec is None or common_spec.loader is None:
        raise RuntimeError("Could not load gov-transparency common module")
    common_module = importlib.util.module_from_spec(common_spec)
    sys.modules[common_spec.name] = common_module
    common_spec.loader.exec_module(common_module)
    load_sibling_module = common_module.load_sibling_module
    parse_period = common_module.parse_period
    normalise = load_sibling_module(Path(__file__).resolve().parents[1] / "normalise.py", __name__, "normalise").normalise
    fingerprint = load_sibling_module(Path(__file__).resolve().parents[1] / "fingerprint.py", __name__, "fingerprint").fingerprint
    extract = load_sibling_module(Path(__file__).resolve().parents[1] / "extract.py", __name__, "extract").extract
    emit_entities = load_sibling_module(Path(__file__).resolve().parents[1] / "entities.py", __name__, "entities").emit_entities
    schema_module = load_sibling_module(Path(__file__).resolve().parents[1] / "schema.py", __name__, "schema")
    SCHEMAS_DIR = schema_module.SCHEMAS_DIR
    load_schema = schema_module.load_schema
    schema_from_dict = schema_module.schema_from_dict
    validate_schema = schema_module.validate_schema
    Provenance = load_sibling_module(Path(__file__).resolve().parents[1] / "types.py", __name__, "types").Provenance


ROOT = Path(__file__).resolve().parents[3]
BASELINE_DIR = Path(__file__).with_name("baseline")
CASES_PATH = BASELINE_DIR / "cases.json"
SUMMARY_PATH = BASELINE_DIR / "summary.json"
REGISTRY_SNAPSHOT_PATH = BASELINE_DIR / "registry_snapshot.json"


@dataclass(frozen=True)
class BaselineCase:
    name: str
    resource_path: str
    department: str
    collection_type: str
    publication_title: str
    attachment_title: str


class CountingDataset:
    def __init__(self):
        self.prefix = "gb-gov-baseline"
        self.emitted = []

    def make(self, schema: str):
        from followthemoney.statement.entity import StatementEntity
        from followthemoney import Dataset as FTMDataset

        if not hasattr(self, "ftm"):
            self.ftm = FTMDataset.make({"name": "gb_gov_transparency_baseline", "prefix": self.prefix})
        return StatementEntity(self.ftm, {"schema": schema})

    def make_id(self, *parts, **kwargs):
        return make_hashed_id(self.prefix, *parts)

    def emit(self, entity):
        self.emitted.append(entity)


def load_cases() -> list[BaselineCase]:
    with CASES_PATH.open("r", encoding="utf-8") as fh:
        raw_cases = json.load(fh)
    cases = []
    for raw_case in raw_cases:
        cases.append(BaselineCase(**raw_case))
    return cases


def make_case_url(case: BaselineCase) -> str:
    return f"https://example.test/{case.name}"


def make_provenance(case: BaselineCase) -> "ProvenanceT":
    period_start, period_end = parse_period(case.publication_title)
    if period_start is None or period_end is None:
        raise ValueError(f"Could not parse period for baseline case: {case.name}")
    return Provenance(
        department=case.department,
        collection_type=case.collection_type,
        publication_title=case.publication_title,
        attachment_title=case.attachment_title,
        url=make_case_url(case),
        period_start=period_start,
        period_end=period_end,
    )


def schema_path_for(fingerprint_value: str) -> str:
    return str(SCHEMAS_DIR / f"{fingerprint_value}.json")


def count_entity_schemata(entities: list[Any]) -> dict[str, int]:
    counts = Counter(entity.schema.name for entity in entities)
    return dict(sorted(counts.items()))


def summarize_case(case: BaselineCase) -> dict:
    resource = ROOT / case.resource_path
    if not resource.exists():
        raise FileNotFoundError(f"Missing baseline resource: {resource}")

    provenance = make_provenance(case)
    sheets = normalise(resource.read_bytes(), resource.name)
    dataset = CountingDataset()
    case_summary = {
        "name": case.name,
        "resource_path": case.resource_path,
        "publication_title": case.publication_title,
        "attachment_title": case.attachment_title,
        "sheet_count": len(sheets),
        "sheets": [],
    }

    for sheet in sheets:
        sheet_fingerprint = fingerprint(sheet)
        schema = load_schema(sheet_fingerprint)
        sheet_summary = {
            "sheet_name": sheet.name,
            "row_count": len(sheet.rows),
            "fingerprint": sheet_fingerprint,
            "schema_path": schema_path_for(sheet_fingerprint) if schema is not None else None,
        }
        if schema is None:
            sheet_summary["status"] = "schema_missing"
            case_summary["sheets"].append(sheet_summary)
            continue

        validate_schema(schema, sheet)
        records = extract(sheet, schema, provenance)

        start_index = len(dataset.emitted)
        emitted_count = 0
        for record in records:
            emitted_count += emit_entities(dataset, record, provenance, schema)
        emitted_entities = dataset.emitted[start_index:]

        sheet_summary.update(
            {
                "status": "validated",
                "sheet_type": schema.sheet_type,
                "activity_type": schema.activity_type,
                "record_count": len(records),
                "entity_count": emitted_count,
                "entity_schemata": count_entity_schemata(emitted_entities),
            }
        )
        case_summary["sheets"].append(sheet_summary)

    case_summary["total_entity_count"] = len(dataset.emitted)
    case_summary["total_entity_schemata"] = count_entity_schemata(dataset.emitted)
    return case_summary


def snapshot_registry() -> dict:
    files = sorted(SCHEMAS_DIR.glob("*.json"))
    by_sheet_type = Counter()
    by_activity_type = Counter()
    fingerprints = []
    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            raw_schema = json.load(fh)
        schema = schema_from_dict(raw_schema)
        fingerprints.append(schema.fingerprint)
        by_sheet_type[schema.sheet_type] += 1
        if schema.activity_type is not None:
            by_activity_type[schema.activity_type] += 1
    return {
        "schema_count": len(files),
        "fingerprints": fingerprints,
        "by_sheet_type": dict(sorted(by_sheet_type.items())),
        "by_activity_type": dict(sorted(by_activity_type.items())),
    }


def main() -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    summary = {
        "cases": [summarize_case(case) for case in cases],
    }
    with SUMMARY_PATH.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")

    with REGISTRY_SNAPSHOT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(snapshot_registry(), fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"Wrote baseline summary to {SUMMARY_PATH}")
    print(f"Wrote registry snapshot to {REGISTRY_SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
