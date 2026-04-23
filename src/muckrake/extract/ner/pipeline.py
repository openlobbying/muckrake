import logging
from pathlib import Path
from typing import Iterable, Optional

from followthemoney.statement.serialize import read_pack_statements

from muckrake.dataset import find_datasets, load_config
from muckrake.runs import resolve_dataset_pack

from .engines import get_extractor
from .engines.base import RecoverableExtractionError
from .materialize import text_fingerprint
from .storage import (
    Candidate,
    get_connection,
    init_db,
    load_cached_keys,
    upsert_candidate,
)

log = logging.getLogger(__name__)

TARGET_FIELDS = {
    ("LegalEntity", "name"),
    ("Organization", "name"),
    ("Company", "name"),
    ("Person", "name"),
}

DEFAULT_EXTRACTOR_VERSION = "default"


def is_complex_text(value: str) -> bool:
    lowered = value.lower()
    if len(value.strip()) < 20:
        return False
    markers = [",", ";", "(", ")", " and ", " & ", ":"]
    return any(marker in lowered for marker in markers)


def iter_text_statements(pack_path: Path) -> Iterable[tuple[str, str, str, str]]:
    with open(pack_path, "rb") as fh:
        for stmt in read_pack_statements(fh):
            if (stmt.schema, stmt.prop) not in TARGET_FIELDS:
                continue
            if not isinstance(stmt.value, str):
                continue
            text = stmt.value.strip()
            if not text:
                continue
            yield stmt.entity_id, stmt.schema, stmt.prop, text


def run_ner_extract(
    dataset_name: Optional[str] = None,
    limit: Optional[int] = None,
    entity_id: Optional[str] = None,
    extractor_name: str = "delimiter",
) -> None:
    configs = find_datasets(dataset_name)
    if not configs:
        log.error("No datasets found matching '%s'", dataset_name)
        return

    extractor = get_extractor(extractor_name)

    conn = get_connection()
    init_db(conn)

    processed = 0
    written = 0
    cached = 0
    skipped = 0

    for config in configs:
        ds = load_config(config)
        try:
            _, pack_path = resolve_dataset_pack(ds.name)
        except ValueError as exc:
            log.warning(str(exc))
            continue

        existing = load_cached_keys(
            conn,
            dataset=ds.name,
            extractor=extractor_name,
            extractor_version=DEFAULT_EXTRACTOR_VERSION,
        )

        seen: set[tuple[str, str, str]] = set()
        for stmt_entity_id, schema, prop, text in iter_text_statements(pack_path):
            if limit is not None and processed >= limit:
                break
            if entity_id is not None and stmt_entity_id != entity_id:
                continue

            key = (stmt_entity_id, prop, text)
            if key in seen:
                continue
            seen.add(key)

            if not is_complex_text(text):
                continue

            fingerprint = text_fingerprint(text)
            cache_key = (stmt_entity_id, prop, fingerprint)
            if cache_key in existing:
                cached += 1
                continue

            try:
                extraction = extractor.extract(text)
            except RecoverableExtractionError as exc:
                skipped += 1
                log.warning(
                    "Skipping extraction for %s:%s due to recoverable extractor error: %s",
                    stmt_entity_id,
                    prop,
                    exc,
                )
                continue
            candidate = Candidate(
                dataset=ds.name,
                entity_id=stmt_entity_id,
                schema=schema,
                property_name=prop,
                source_text=text,
                fingerprint=fingerprint,
                extractor=extractor_name,
                extractor_version=DEFAULT_EXTRACTOR_VERSION,
                extraction=extraction,
            )

            processed += 1
            if upsert_candidate(conn, candidate):
                written += 1
                existing.add(cache_key)

        if limit is not None and processed >= limit:
            break

    conn.close()
    log.info(
        "NER extract complete. Processed=%s candidates, cached=%s, skipped=%s, upserted=%s entries.",
        processed,
        cached,
        skipped,
        written,
    )
