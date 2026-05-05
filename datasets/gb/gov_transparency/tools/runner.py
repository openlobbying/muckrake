from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

from followthemoney.statement.serialize import PackStatementWriter
from muckrake.dataset import Dataset

try:
    from ..common import load_sibling_module
    from ..crawler import (
        iter_collection_configs,
        iter_collection_sources,
        load_incremental_manifest,
        load_source_reference,
        should_skip_source,
        should_use_incremental_manifest,
    )
    from ..fingerprint import detect_header_row, fingerprint, header_signature
    from ..normalise import detect_file_format, normalise
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
    load_incremental_manifest = crawler_module.load_incremental_manifest
    load_source_reference = crawler_module.load_source_reference
    should_skip_source = crawler_module.should_skip_source
    should_use_incremental_manifest = crawler_module.should_use_incremental_manifest
    fingerprint_module = load_sibling_module(Path(__file__).resolve().parents[1] / "fingerprint.py", __name__, "fingerprint")
    detect_header_row = fingerprint_module.detect_header_row
    fingerprint = fingerprint_module.fingerprint
    header_signature = fingerprint_module.header_signature
    normalise_module = load_sibling_module(Path(__file__).resolve().parents[1] / "normalise.py", __name__, "normalise")
    detect_file_format = normalise_module.detect_file_format
    normalise = normalise_module.normalise


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


def iter_crawl_order_sheets(skip_processed: bool = True):
    dataset = make_dataset()
    try:
        incremental_manifest = load_incremental_manifest(dataset) if should_use_incremental_manifest(dataset) else None
        for collection in iter_collection_configs(dataset):
            for filename, provenance in iter_collection_sources(dataset, collection):
                source_reference = load_source_reference(dataset, filename, provenance)
                if source_reference.data is None:
                    continue
                if skip_processed and incremental_manifest is not None and should_skip_source(incremental_manifest, provenance, source_reference):
                    continue
                if detect_file_format(source_reference.data, filename) is None:
                    continue
                try:
                    sheets = normalise(source_reference.data, filename)
                except Exception:
                    continue
                for sheet in sheets:
                    sheet_fingerprint = fingerprint(sheet)
                    yield dataset, provenance, source_reference, sheet, sheet_fingerprint
    finally:
        dataset.close()
