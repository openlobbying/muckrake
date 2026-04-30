import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from requests import HTTPError

from muckrake.dataset import Dataset

try:
    from .common import load_sibling_module, parse_period, slugify
    from .entities import emit_entities
    from .extract import extract
    from .fingerprint import fingerprint
    from .normalise import normalise
    from .schema import load_schema, validate_schema
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
    slugify = common_module.slugify
    normalise = load_sibling_module(__file__, __name__, "normalise").normalise
    fingerprint = load_sibling_module(__file__, __name__, "fingerprint").fingerprint
    extract = load_sibling_module(__file__, __name__, "extract").extract
    entities_module = load_sibling_module(__file__, __name__, "entities")
    emit_entities = entities_module.emit_entities
    schema_module = load_sibling_module(__file__, __name__, "schema")
    load_schema = schema_module.load_schema
    validate_schema = schema_module.validate_schema
    Provenance = load_sibling_module(__file__, __name__, "types").Provenance

GOVUK_URL = "https://www.gov.uk"
GOVUK_CONTENT_API_URL = "https://www.gov.uk/api/content"
CONTENT_CACHE_DAYS = 7
RESOURCE_CACHE_DAYS = 30


@dataclass(frozen=True)
class CollectionConfig:
    department: str
    collection_url: str
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
            raise ValueError(
                f"gov-transparency department '{department_name}' must define collection_urls as a list"
            )
        for collection_url in collection_urls:
            if not isinstance(collection_url, str) or not collection_url.strip():
                raise ValueError(
                    f"gov-transparency department '{department_name}' collection_urls must contain only strings"
                )
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
) -> Provenance:
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


def iter_publication_sources(
    department: str,
    collection_url: str,
    publication_path: str,
    publication: dict,
):
    details = publication.get("details", {})
    if not isinstance(details, dict):
        raise ValueError(f"Publication API response for {publication_path} must define details as an object")

    attachments = details.get("attachments", [])
    if not isinstance(attachments, list):
        raise ValueError(
            f"Publication API response for {publication_path} must define details.attachments as a list"
        )

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


def fetch_source_bytes(dataset: Dataset, filename: str, provenance: Provenance) -> bytes | None:
    suffix = Path(filename).suffix.lower()
    if suffix in {".html", ".htm"}:
        text = dataset.fetch_text(provenance.url, cache_days=RESOURCE_CACHE_DAYS)
        if text is None:
            raise ValueError(f"Failed to fetch HTML source: {provenance.url}")
        return text.encode("utf-8")

    resource_name = "/".join(
        part
        for part in [provenance.collection_type, Path(urlparse(provenance.url).path).parent.name, filename]
        if part
    )
    path = fetch_resource_or_warn(dataset, resource_name, provenance.url)
    if path is None:
        return None
    return path.read_bytes()


def report_unknown_fingerprint(dataset: Dataset, provenance: Provenance, sheet, sheet_fingerprint: str) -> None:
    dataset.log.warning("UNKNOWN FINGERPRINT: %s", sheet_fingerprint)
    dataset.log.warning(
        "department=%s publication=%s attachment=%s url=%s",
        provenance.department,
        provenance.publication_title,
        provenance.attachment_title,
        provenance.url,
    )
    for line in format_sheet_preview(sheet.rows[:30]):
        dataset.log.warning("%s", line)


def format_sheet_preview(rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["<empty sheet>"]
    width = max((len(row) for row in rows), default=0)
    padded = [row + [""] * (width - len(row)) for row in rows]
    column_widths = [max(len(row[index]) for row in padded) for index in range(width)]
    output = []
    for row in padded:
        output.append(" | ".join(cell.ljust(column_widths[index]) for index, cell in enumerate(row)).rstrip())
    return output


def should_fail_on_unknown(dataset: Dataset) -> bool:
    value = dataset._data.get("fail_on_unknown", True)
    return bool(value)


def crawl(dataset: Dataset):
    stats = {
        "sources_processed": 0,
        "sheets_processed": 0,
        "unknown_fingerprints": 0,
        "validated_sheets": 0,
        "entities_emitted": 0,
    }

    for collection in iter_collection_configs(dataset):
        for filename, provenance in iter_collection_sources(dataset, collection):
            process_source(dataset, filename, provenance, stats)

    dataset.log.info(
        "gov-transparency discovery summary: %d sources fetched, %d sheets normalised, %d sheets with schema, %d unknown fingerprints, %d entities emitted",
        stats["sources_processed"],
        stats["sheets_processed"],
        stats["validated_sheets"],
        stats["unknown_fingerprints"],
        stats["entities_emitted"],
    )


def iter_collection_sources(dataset: Dataset, collection: CollectionConfig):
    collection_data = fetch_json_or_warn(
        dataset,
        make_content_api_url(collection.collection_url),
        "collection",
    )
    if collection_data is None:
        return
    if not isinstance(collection_data, dict):
        raise ValueError(f"Expected a JSON object from GOV.UK collection API: {collection.collection_url}")

    links = collection_data.get("links", {})
    if not isinstance(links, dict):
        raise ValueError(
            f"Collection API response for {collection.collection_url} must define links as an object"
        )
    documents = links.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError(
            f"Collection API response for {collection.collection_url} must define links.documents as a list"
        )

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError(f"Collection document entry must be a mapping: {collection.collection_url}")
        publication_path = document.get("base_path")
        if not isinstance(publication_path, str) or not publication_path.strip():
            raise ValueError(f"Collection API document is missing a base_path: {collection.collection_url}")

        publication = fetch_json_or_warn(
            dataset,
            make_content_api_url(publication_path),
            f"publication {publication_path}",
        )
        if publication is None:
            continue
        if not isinstance(publication, dict):
            raise ValueError(f"Expected a JSON object from GOV.UK publication API: {publication_path}")

        yield from iter_publication_sources(
            collection.department,
            collection.collection_url,
            publication_path,
            publication,
        )


def process_source(dataset: Dataset, filename: str, provenance: Provenance, stats: dict[str, int]) -> None:
    data = fetch_source_bytes(dataset, filename, provenance)
    if data is None:
        return
    sheets = normalise(data, filename)
    stats["sources_processed"] += 1
    stats["sheets_processed"] += len(sheets)
    parsed_sheets: list[str] = []
    for sheet in sheets:
        summary = process_sheet(dataset, sheet, provenance, stats)
        if summary is not None:
            parsed_sheets.append(summary)
    # if sheets:
    #     dataset.log.info(
    #         "Processed %s sheets=%d parsed=%s",
    #         provenance.attachment_title,
    #         len(sheets),
    #         ", ".join(parsed_sheets) or "none",
    #     )


def process_sheet(dataset: Dataset, sheet, provenance: Provenance, stats: dict[str, int]) -> str | None:
    sheet_fingerprint = fingerprint(sheet)
    schema = load_schema(sheet_fingerprint)
    if schema is None:
        stats["unknown_fingerprints"] += 1
        report_unknown_fingerprint(dataset, provenance, sheet, sheet_fingerprint)
        if should_fail_on_unknown(dataset):
            raise ValueError(f"UNKNOWN FINGERPRINT: {sheet_fingerprint}")
        return None
    validate_schema(schema, sheet)
    stats["validated_sheets"] += 1
    for record in extract(sheet, schema, provenance):
        stats["entities_emitted"] += emit_entities(dataset, record, provenance, schema)
    return f"{sheet.name}:{sheet_fingerprint}"
