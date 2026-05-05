from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import muckrake  # ensure custom FtM schemata are registered before model use
from followthemoney.statement.serialize import PackStatementWriter

from muckrake.dataset import Dataset

try:
    from ..common import load_sibling_module
    from ..crawler import (
        iter_collection_configs,
        iter_collection_sources,
        make_source_key,
        load_incremental_manifest,
        load_source_reference,
        save_incremental_manifest,
        schema_registry_signature,
        should_skip_source,
        should_use_incremental_manifest,
    )
    from ..entities import emit_entities
    from ..extract import extract
    from ..fingerprint import detect_header_row, fingerprint, header_signature
    from ..normalise import detect_file_format, normalise
    from ..rows import evaluate_rows
    from ..schema import load_schema, validate_schema
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
    crawler_module = load_sibling_module(Path(__file__).resolve().parents[1] / "crawler.py", __name__, "crawler")
    iter_collection_configs = crawler_module.iter_collection_configs
    iter_collection_sources = crawler_module.iter_collection_sources
    make_source_key = crawler_module.make_source_key
    load_incremental_manifest = crawler_module.load_incremental_manifest
    load_source_reference = crawler_module.load_source_reference
    save_incremental_manifest = crawler_module.save_incremental_manifest
    schema_registry_signature = crawler_module.schema_registry_signature
    should_skip_source = crawler_module.should_skip_source
    should_use_incremental_manifest = crawler_module.should_use_incremental_manifest
    emit_entities = load_sibling_module(Path(__file__).resolve().parents[1] / "entities.py", __name__, "entities").emit_entities
    extract = load_sibling_module(Path(__file__).resolve().parents[1] / "extract.py", __name__, "extract").extract
    fingerprint_module = load_sibling_module(Path(__file__).resolve().parents[1] / "fingerprint.py", __name__, "fingerprint")
    detect_header_row = fingerprint_module.detect_header_row
    fingerprint = fingerprint_module.fingerprint
    header_signature = fingerprint_module.header_signature
    normalise_module = load_sibling_module(Path(__file__).resolve().parents[1] / "normalise.py", __name__, "normalise")
    detect_file_format = normalise_module.detect_file_format
    normalise = normalise_module.normalise
    evaluate_rows = load_sibling_module(Path(__file__).resolve().parents[1] / "rows.py", __name__, "rows").evaluate_rows
    schema_module = load_sibling_module(Path(__file__).resolve().parents[1] / "schema.py", __name__, "schema")
    load_schema = schema_module.load_schema
    validate_schema = schema_module.validate_schema


CONFIG_PATH = Path("datasets/gb/gov_transparency/config.yml")


def make_dataset() -> Dataset:
    temp = tempfile.NamedTemporaryFile("w")
    return Dataset(CONFIG_PATH, PackStatementWriter(temp), timestamps={})


def make_preview(sheet) -> list[list[str]]:
    header_row = detect_header_row(sheet)
    return sheet.rows[header_row : header_row + 8]


def make_context(provenance, source_reference, sheet, sheet_fingerprint: str) -> dict[str, object]:
    return {
        "fingerprint": sheet_fingerprint,
        "resource": str(source_reference.resource_path) if source_reference.resource_path is not None else None,
        "sheet": sheet.name,
        "header_row": detect_header_row(sheet),
        "signature": header_signature(sheet),
        "preview": make_preview(sheet),
        "publication_title": provenance.publication_title,
        "attachment_title": provenance.attachment_title,
        "url": provenance.url,
    }


def blocker_status_for_source(manifest: dict[str, object], provenance, source_reference) -> str | None:
    source_entry = manifest.get("sources", {}).get(make_source_key(provenance))
    if not isinstance(source_entry, dict):
        return None
    if source_entry.get("source_signature") != source_reference.source_signature:
        return None
    if source_entry.get("schema_registry_signature") != schema_registry_signature():
        return None
    status = source_entry.get("status")
    if status == "blocker_clear":
        return status
    return None


def mark_source_blocker_clear(manifest: dict[str, object], provenance, source_reference) -> None:
    manifest.setdefault("sources", {})[make_source_key(provenance)] = {
        "url": provenance.url,
        "resource_path": str(source_reference.resource_path) if source_reference.resource_path is not None else None,
        "source_signature": source_reference.source_signature,
        "schema_registry_signature": schema_registry_signature(),
        "status": "blocker_clear",
    }


def main() -> int:
    dataset = make_dataset()
    try:
        incremental_manifest = load_incremental_manifest(dataset) if should_use_incremental_manifest(dataset) else None
        for collection in iter_collection_configs(dataset):
            for filename, provenance in iter_collection_sources(dataset, collection):
                source_reference = load_source_reference(dataset, filename, provenance)
                if source_reference.data is None:
                    continue
                if incremental_manifest is not None and should_skip_source(incremental_manifest, provenance, source_reference):
                    continue
                if incremental_manifest is not None and blocker_status_for_source(incremental_manifest, provenance, source_reference) == "blocker_clear":
                    continue
                if detect_file_format(source_reference.data, filename) is None:
                    continue
                try:
                    sheets = normalise(source_reference.data, filename)
                except Exception as exc:
                    print(json.dumps({"status": "parse_error", "error": str(exc), "resource": str(source_reference.resource_path)}, indent=2, ensure_ascii=False))
                    return 1
                for sheet in sheets:
                    sheet_fingerprint = fingerprint(sheet)
                    context = make_context(provenance, source_reference, sheet, sheet_fingerprint)
                    schema = load_schema(sheet_fingerprint)
                    if schema is None:
                        context["status"] = "unknown_fingerprint"
                        print(json.dumps(context, indent=2, ensure_ascii=False))
                        return 0
                    try:
                        validate_schema(schema, sheet)
                    except Exception as exc:
                        context["status"] = "schema_validation_failed"
                        context["error"] = str(exc)
                        print(json.dumps(context, indent=2, ensure_ascii=False))
                        return 0
                    try:
                        records = extract(sheet, schema, provenance)
                    except Exception as exc:
                        context["status"] = "extraction_failed"
                        context["error"] = str(exc)
                        print(json.dumps(context, indent=2, ensure_ascii=False))
                        return 0
                    for record in records:
                        try:
                            emit_entities(dataset, record, provenance, schema)
                        except Exception as exc:
                            context["status"] = "entity_emission_failed"
                            context["error"] = str(exc)
                            context["record"] = record
                            print(json.dumps(context, indent=2, ensure_ascii=False))
                            return 0
                if incremental_manifest is not None:
                    mark_source_blocker_clear(incremental_manifest, provenance, source_reference)
        print("NO_BLOCKER")
        return 0
    finally:
        if incremental_manifest is not None:
            save_incremental_manifest(dataset, incremental_manifest)
        dataset.close()


if __name__ == "__main__":
    raise SystemExit(main())
