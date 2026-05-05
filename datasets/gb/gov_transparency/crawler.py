from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from requests import HTTPError

from muckrake.dataset import Dataset

if TYPE_CHECKING:
    from .normalise import NormalisedSheet as NormalisedSheetT
    from .trace import TraceWriter as TraceWriterT
    from .types import Provenance as ProvenanceT

try:
    from .common import load_sibling_module, parse_period
    from .entities import emit_entities
    from .extract import extract
    from .fingerprint import detect_header_row, fingerprint, header_signature
    from .normalise import detect_file_format, normalise
    from .rows import evaluate_rows
    from .schema import load_schema, validate_schema
    from .trace import NullTraceWriter, TraceWriter
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
    load_sibling_module = common_module.load_sibling_module
    parse_period = common_module.parse_period
    normalise_module = load_sibling_module(__file__, __name__, "normalise")
    detect_file_format = normalise_module.detect_file_format
    normalise = normalise_module.normalise
    fingerprint_module = load_sibling_module(__file__, __name__, "fingerprint")
    detect_header_row = fingerprint_module.detect_header_row
    header_signature = fingerprint_module.header_signature
    fingerprint = fingerprint_module.fingerprint
    extract = load_sibling_module(__file__, __name__, "extract").extract
    emit_entities = load_sibling_module(__file__, __name__, "entities").emit_entities
    rows_module = load_sibling_module(__file__, __name__, "rows")
    evaluate_rows = rows_module.evaluate_rows
    schema_module = load_sibling_module(__file__, __name__, "schema")
    load_schema = schema_module.load_schema
    validate_schema = schema_module.validate_schema
    trace_module = load_sibling_module(__file__, __name__, "trace")
    TraceWriter = trace_module.TraceWriter
    NullTraceWriter = trace_module.NullTraceWriter
    Provenance = load_sibling_module(__file__, __name__, "types").Provenance

GOVUK_URL = "https://www.gov.uk"
GOVUK_CONTENT_API_URL = "https://www.gov.uk/api/content"
CONTENT_CACHE_DAYS = 7
RESOURCE_CACHE_DAYS = 30
INCREMENTAL_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class CollectionConfig:
    department: str
    collection_url: str


@dataclass(frozen=True)
class SourceReference:
    data: bytes | None
    resource_path: Path | None
    fetch_status: str
    source_signature: str


def iter_collection_configs(dataset: Dataset):
    collections = dataset._data.get("collections")
    if collections is not None:
        if not isinstance(collections, list):
            raise ValueError("gov-transparency config must define 'collections' as a list")
        for collection in collections:
            if not isinstance(collection, str) or not collection.strip():
                raise ValueError("gov-transparency collections must contain non-empty strings")
            yield CollectionConfig(department="", collection_url=collection.strip())

    departments = dataset._data.get("departments", [])
    if not isinstance(departments, list):
        raise ValueError("gov-transparency config must define 'departments' as a list")

    for department in departments:
        if not isinstance(department, dict):
            raise ValueError("each gov-transparency department must be a mapping")
        department_name = department.get("name")
        if not isinstance(department_name, str) or not department_name.strip():
            raise ValueError("each gov-transparency department must define a non-empty name")
        collection_urls = department.get("collection_urls", [])
        if not isinstance(collection_urls, list):
            raise ValueError(f"gov-transparency department '{department_name}' must define collection_urls as a list")
        for collection_url in collection_urls:
            if not isinstance(collection_url, str) or not collection_url.strip():
                raise ValueError(f"gov-transparency department '{department_name}' collection_urls must contain only strings")
            yield CollectionConfig(department=department_name, collection_url=collection_url.strip())


def make_content_api_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        path = urlparse(value).path.rstrip("/")
    elif value.startswith("/"):
        path = value.rstrip("/")
    else:
        slug = value.strip().strip("/")
        path = f"/government/collections/{slug}"
    if not path:
        raise ValueError(f"Could not derive GOV.UK content API path from value: {value}")
    return f"{GOVUK_CONTENT_API_URL}{path}"


def fetch_json_or_warn(dataset: Dataset, url: str, label: str):
    try:
        return dataset.fetch_json(url, cache_days=CONTENT_CACHE_DAYS)
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code in [404, 410]:
            dataset.log.warning("Skipping missing %s: %s", label, url)
            return None
        raise


def fetch_resource_or_warn(dataset: Dataset, name: str, url: str):
    try:
        return dataset.fetch_resource(name, url)
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code in [404, 410]:
            dataset.log.warning("Skipping missing attachment: %s", url)
            return None
        raise


def incremental_manifest_path(dataset: Dataset) -> Path:
    return dataset.data_path / "incremental-manifest.json"


def should_use_incremental_manifest(dataset: Dataset) -> bool:
    value = dataset._data.get("incremental_manifest_enabled", True)
    return bool(value)


def load_incremental_manifest(dataset: Dataset) -> dict[str, Any]:
    path = incremental_manifest_path(dataset)
    if not path.exists():
        return {"version": INCREMENTAL_MANIFEST_VERSION, "sources": {}}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        return {"version": INCREMENTAL_MANIFEST_VERSION, "sources": {}}
    if payload.get("version") != INCREMENTAL_MANIFEST_VERSION:
        return {"version": INCREMENTAL_MANIFEST_VERSION, "sources": {}}
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        return {"version": INCREMENTAL_MANIFEST_VERSION, "sources": {}}
    return {"version": INCREMENTAL_MANIFEST_VERSION, "sources": sources}


def save_incremental_manifest(dataset: Dataset, manifest: dict[str, Any]) -> None:
    path = incremental_manifest_path(dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


@lru_cache(maxsize=1)
def schema_registry_signature() -> str:
    digest = hashlib.sha256()
    schema_dir = Path(__file__).with_name("schemas")
    for path in sorted(schema_dir.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def make_source_key(provenance: "ProvenanceT") -> str:
    return provenance.url


def make_source_signature(resource_path: Path | None, data: bytes | None) -> str:
    if data is None:
        return "missing"
    digest = hashlib.sha256(data).hexdigest()
    return f"bytes:{digest}:{len(data)}"


def load_source_reference(dataset: Dataset, filename: str, provenance: "ProvenanceT") -> SourceReference:
    data, resource_path, fetch_status = fetch_source_bytes(dataset, filename, provenance)
    return SourceReference(
        data=data,
        resource_path=resource_path,
        fetch_status=fetch_status,
        source_signature=make_source_signature(resource_path, data),
    )


def should_skip_source(
    manifest: dict[str, Any],
    provenance: "ProvenanceT",
    source_reference: SourceReference,
) -> bool:
    source_entry = manifest.get("sources", {}).get(make_source_key(provenance))
    if not isinstance(source_entry, dict):
        return False
    return (
        source_entry.get("source_signature") == source_reference.source_signature
        and source_entry.get("schema_registry_signature") == schema_registry_signature()
        and source_entry.get("status") == "processed"
    )


def update_manifest_for_source(
    manifest: dict[str, Any],
    provenance: "ProvenanceT",
    source_reference: SourceReference,
    *,
    status: str,
    file_format: str | None,
    sheet_fingerprints: list[str] | None = None,
) -> None:
    manifest.setdefault("sources", {})[make_source_key(provenance)] = {
        "url": provenance.url,
        "resource_path": str(source_reference.resource_path) if source_reference.resource_path is not None else None,
        "source_signature": source_reference.source_signature,
        "schema_registry_signature": schema_registry_signature(),
        "status": status,
        "file_format": file_format,
        "sheet_fingerprints": sheet_fingerprints or [],
    }


def get_attachment_filename(attachment: dict, publication_path: str) -> str:
    filename = attachment.get("filename")
    if isinstance(filename, str) and filename.strip():
        return filename.strip()

    attachment_url = attachment.get("url")
    if isinstance(attachment_url, str) and attachment_url.strip():
        fallback = Path(urlparse(attachment_url).path).name
        if fallback:
            return fallback

    raise ValueError(f"Publication {publication_path} has an attachment without a filename")


def publication_title(publication: dict, publication_path: str) -> str:
    title = publication.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    raise ValueError(f"Publication {publication_path} is missing a title")


def collection_type_from_url(collection_url: str) -> str:
    path = urlparse(collection_url).path if collection_url.startswith("http") else collection_url
    return Path(path.rstrip("/")).name


def build_provenance(
    department: str,
    collection_url: str,
    publication_path: str,
    publication: dict,
    attachment_title: str,
    source_url: str,
) -> "ProvenanceT":
    title = publication_title(publication, publication_path)
    period_start, period_end = parse_period(title)
    if period_start is None and period_end is None:
        period_start, period_end = parse_period(Path(publication_path.rstrip("/")).name)
    return Provenance(
        department=department.strip() if department else "",
        collection_type=collection_type_from_url(collection_url),
        publication_title=title,
        attachment_title=attachment_title,
        url=source_url,
        period_start=period_start,
        period_end=period_end,
    )


def iter_publication_sources(department: str, collection_url: str, publication_path: str, publication: dict):
    details = publication.get("details", {})
    if not isinstance(details, dict):
        raise ValueError(f"Publication API response for {publication_path} must define details as an object")

    attachments = details.get("attachments", [])
    if not isinstance(attachments, list):
        raise ValueError(f"Publication API response for {publication_path} must define details.attachments as a list")

    yielded_attachment = False
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise ValueError(f"Publication attachment entry must be a mapping: {publication_path}")
        attachment_url = attachment.get("url")
        if not isinstance(attachment_url, str) or not attachment_url.strip():
            continue
        yielded_attachment = True
        source_url = urljoin(GOVUK_URL, attachment_url)
        attachment_title = attachment.get("title")
        if not isinstance(attachment_title, str) or not attachment_title.strip():
            attachment_title = get_attachment_filename(attachment, publication_path)
        yield get_attachment_filename(attachment, publication_path), build_provenance(
            department,
            collection_url,
            publication_path,
            publication,
            attachment_title.strip(),
            source_url,
        )

    if yielded_attachment:
        return

    publication_url = urljoin(GOVUK_URL, publication_path)
    title = publication_title(publication, publication_path)
    publication_slug = Path(publication_path.rstrip("/")).name or "publication"
    yield f"{publication_slug}.html", build_provenance(
        department,
        collection_url,
        publication_path,
        publication,
        title,
        publication_url,
    )


def fetch_source_bytes(dataset: Dataset, filename: str, provenance: "ProvenanceT") -> tuple[bytes | None, Path | None, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".html", ".htm"}:
        text = dataset.fetch_text(provenance.url, cache_days=RESOURCE_CACHE_DAYS)
        if text is None:
            raise ValueError(f"Failed to fetch HTML source: {provenance.url}")
        return text.encode("utf-8"), None, "normalised"

    resource_name = "/".join(
        part for part in [provenance.collection_type, Path(urlparse(provenance.url).path).parent.name, filename] if part
    )
    path = fetch_resource_or_warn(dataset, resource_name, provenance.url)
    if path is None:
        return None, None, "missing"
    return path.read_bytes(), path, "normalised"


def report_unknown_fingerprint(
    dataset: Dataset,
    provenance: "ProvenanceT",
    resource_path: Path | None,
    sheet: "NormalisedSheetT",
    sheet_fingerprint: str,
) -> None:
    dataset.log.warning("UNKNOWN FINGERPRINT: %s", sheet_fingerprint)
    dataset.log.warning(
        "department=%s publication=%s attachment=%s url=%s resource=%s header_row=%s signature=%s",
        provenance.department,
        provenance.publication_title,
        provenance.attachment_title,
        provenance.url,
        resource_path,
        detect_header_row(sheet),
        header_signature(sheet),
    )
    preview_start = detect_header_row(sheet)
    for line in format_sheet_preview(sheet.rows[preview_start : preview_start + 8]):
        dataset.log.warning("%s", line)


def format_sheet_preview(rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["<empty sheet>"]
    width = max((last_non_empty_index(row) + 1 for row in rows), default=0)
    padded = [row + [""] * (width - len(row)) for row in rows]
    column_widths = [max(len(row[index]) for row in padded) for index in range(width)]
    output = []
    for row in padded:
        output.append(" | ".join(row[index].ljust(column_widths[index]) for index in range(width)).rstrip())
    return output


def last_non_empty_index(row: list[str]) -> int:
    for index in range(len(row) - 1, -1, -1):
        if row[index].strip():
            return index
    return -1


def should_fail_on_unknown(dataset: Dataset) -> bool:
    value = dataset._data.get("fail_on_unknown", True)
    return bool(value)


def should_continue_on_error(dataset: Dataset) -> bool:
    value = dataset._data.get("continue_on_error", False)
    return bool(value)


def should_write_trace(dataset: Dataset) -> bool:
    value = dataset._data.get("trace_enabled", False)
    return bool(value)


def crawl(dataset: Dataset):
    trace_path = dataset.data_path / "trace" / "manifest.jsonl"
    trace = TraceWriter(trace_path) if should_write_trace(dataset) else NullTraceWriter()
    incremental_manifest = load_incremental_manifest(dataset) if should_use_incremental_manifest(dataset) else None
    stats = {
        "sources_processed": 0,
        "sources_skipped": 0,
        "sheets_processed": 0,
        "unknown_fingerprints": 0,
        "validated_sheets": 0,
        "entities_emitted": 0,
        "source_errors": 0,
    }

    try:
        for collection in iter_collection_configs(dataset):
            for filename, provenance in iter_collection_sources(dataset, collection):
                try:
                    process_source(dataset, filename, provenance, stats, trace, incremental_manifest)
                except Exception as exc:
                    stats["source_errors"] += 1
                    write_source_trace(
                        trace,
                        provenance,
                        filename,
                        resource_path=None,
                        file_format=None,
                        status="source_error",
                        error=str(exc),
                    )
                    if should_continue_on_error(dataset):
                        dataset.log.exception("Failed to process source: %s", provenance.url)
                        continue
                    raise
    finally:
        trace.close()
        if incremental_manifest is not None:
            save_incremental_manifest(dataset, incremental_manifest)

    dataset.log.info(
        "gov-transparency summary: %d sources, %d skipped, %d sheets, %d validated, %d unknown, %d entities, %d source_errors%s",
        stats["sources_processed"],
        stats["sources_skipped"],
        stats["sheets_processed"],
        stats["validated_sheets"],
        stats["unknown_fingerprints"],
        stats["entities_emitted"],
        stats["source_errors"],
        f" trace={trace_path}" if should_write_trace(dataset) else "",
    )


def iter_collection_sources(dataset: Dataset, collection: CollectionConfig):
    collection_data = fetch_json_or_warn(dataset, make_content_api_url(collection.collection_url), "collection")
    if collection_data is None:
        return
    if not isinstance(collection_data, dict):
        raise ValueError(f"Expected a JSON object from GOV.UK collection API: {collection.collection_url}")

    links = collection_data.get("links", {})
    if not isinstance(links, dict):
        raise ValueError(f"Collection API response for {collection.collection_url} must define links as an object")
    documents = links.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError(f"Collection API response for {collection.collection_url} must define links.documents as a list")

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError(f"Collection document entry must be a mapping: {collection.collection_url}")
        publication_path = document.get("base_path")
        if not isinstance(publication_path, str) or not publication_path.strip():
            raise ValueError(f"Collection API document is missing a base_path: {collection.collection_url}")

        publication = fetch_json_or_warn(dataset, make_content_api_url(publication_path), f"publication {publication_path}")
        if publication is None:
            continue
        if not isinstance(publication, dict):
            raise ValueError(f"Expected a JSON object from GOV.UK publication API: {publication_path}")

        yield from iter_publication_sources(collection.department, collection.collection_url, publication_path, publication)


def process_source(
    dataset: Dataset,
    filename: str,
    provenance: "ProvenanceT",
    stats: dict[str, int],
    trace: "TraceWriterT",
    incremental_manifest: dict[str, Any] | None,
) -> None:
    source_reference = load_source_reference(dataset, filename, provenance)
    if source_reference.data is None:
        return

    if incremental_manifest is not None and should_skip_source(incremental_manifest, provenance, source_reference):
        stats["sources_skipped"] += 1
        write_source_trace(
            trace,
            provenance,
            filename,
            source_reference.resource_path,
            file_format=None,
            status="skipped_unchanged",
        )
        return

    file_format = detect_file_format(source_reference.data, filename)
    if file_format is None:
        write_source_trace(trace, provenance, filename, source_reference.resource_path, file_format=None, status="unsupported")
        if incremental_manifest is not None:
            update_manifest_for_source(
                incremental_manifest,
                provenance,
                source_reference,
                status="unsupported",
                file_format=None,
            )
        return

    try:
        sheets = normalise(source_reference.data, filename)
    except Exception as exc:
        write_source_trace(
            trace,
            provenance,
            filename,
            source_reference.resource_path,
            file_format=file_format,
            status="parse_error",
            error=str(exc),
        )
        raise

    status = "empty" if not sheets else source_reference.fetch_status
    if not sheets:
        write_source_trace(trace, provenance, filename, source_reference.resource_path, file_format=file_format, status=status)
        if incremental_manifest is not None:
            update_manifest_for_source(
                incremental_manifest,
                provenance,
                source_reference,
                status=status,
                file_format=file_format,
            )
        return

    stats["sources_processed"] += 1
    stats["sheets_processed"] += len(sheets)
    for sheet in sheets:
        process_sheet(dataset, sheet, provenance, source_reference.resource_path, file_format, stats, trace)

    if incremental_manifest is not None:
        update_manifest_for_source(
            incremental_manifest,
            provenance,
            source_reference,
            status="processed",
            file_format=file_format,
            sheet_fingerprints=[fingerprint(sheet) for sheet in sheets],
        )


def process_sheet(
    dataset: Dataset,
    sheet: "NormalisedSheetT",
    provenance: "ProvenanceT",
    resource_path: Path | None,
    file_format: str,
    stats: dict[str, int],
    trace: "TraceWriterT",
) -> None:
    sheet_fingerprint = fingerprint(sheet)
    header_row_index = detect_header_row(sheet)
    header_preview = header_signature(sheet)
    schema = load_schema(sheet_fingerprint)

    trace_record = {
        "type": "sheet",
        "url": provenance.url,
        "resource_path": str(resource_path) if resource_path is not None else None,
        "publication_title": provenance.publication_title,
        "attachment_title": provenance.attachment_title,
        "sheet_name": sheet.name,
        "file_format": file_format,
        "header_row_index": header_row_index,
        "header_preview": header_preview,
        "fingerprint": sheet_fingerprint,
        "sheet_row_count": len(sheet.rows),
    }

    if schema is None:
        stats["unknown_fingerprints"] += 1
        trace_record["status"] = "schema_missing"
        trace.write(trace_record)
        report_unknown_fingerprint(dataset, provenance, resource_path, sheet, sheet_fingerprint)
        if should_fail_on_unknown(dataset):
            raise ValueError(f"UNKNOWN FINGERPRINT: {sheet_fingerprint}")
        return

    try:
        validate_schema(schema, sheet)
    except Exception as exc:
        raise ValueError(
            "Schema validation failed: "
            f"fingerprint={sheet_fingerprint} schema={Path(__file__).with_name('schemas') / f'{sheet_fingerprint}.json'} "
            f"resource={resource_path} sheet={sheet.name!r} url={provenance.url} error={exc}"
        ) from exc

    stats["validated_sheets"] += 1

    rows, row_stats = evaluate_rows(sheet, schema)
    try:
        records = extract(sheet, schema, provenance)
    except Exception as exc:
        raise ValueError(
            "Extraction failed: "
            f"fingerprint={sheet_fingerprint} schema={Path(__file__).with_name('schemas') / f'{sheet_fingerprint}.json'} "
            f"resource={resource_path} sheet={sheet.name!r} url={provenance.url} error={exc}"
        ) from exc

    emitted_count = 0
    for record in records:
        try:
            emitted_count += emit_entities(dataset, record, provenance, schema)
        except Exception as exc:
            raise ValueError(
                "Entity emission failed: "
                f"fingerprint={sheet_fingerprint} schema={Path(__file__).with_name('schemas') / f'{sheet_fingerprint}.json'} "
                f"resource={resource_path} sheet={sheet.name!r} row_index={record.get('row_index')} "
                f"record={record} url={provenance.url} error={exc}"
            ) from exc
    stats["entities_emitted"] += emitted_count

    trace_record.update(
        {
            "status": "validated",
            "schema_path": str((Path(__file__).with_name("schemas") / f"{sheet_fingerprint}.json")),
            "sheet_type": schema.sheet_type,
            "activity_type": schema.activity_type,
            "row_counts": {
                "total": row_stats.total_rows,
                "candidate": len(rows),
                "records": len(records),
                "skip_prefix": row_stats.skip_prefix_rows,
                "nil": row_stats.nil_rows,
                "blank": row_stats.blank_rows,
                "blank_date": row_stats.blank_date_rows,
                "blank_end_date": row_stats.blank_end_date_rows,
            },
            "emitted_entity_count": emitted_count,
            "sample_row_indexes": [row.row_index for row in rows[:5]],
        }
    )
    trace.write(trace_record)


def write_source_trace(
    trace: "TraceWriterT",
    provenance: "ProvenanceT",
    filename: str,
    resource_path: Path | None,
    file_format: str | None,
    status: str,
    error: str | None = None,
) -> None:
    record = {
        "type": "source",
        "url": provenance.url,
        "resource_path": str(resource_path) if resource_path is not None else None,
        "publication_title": provenance.publication_title,
        "attachment_title": provenance.attachment_title,
        "filename": filename,
        "file_format": file_format,
        "status": status,
    }
    if error is not None:
        record["error"] = error
    trace.write(record)
