import asyncio
import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path

from followthemoney.statement.serialize import read_pack_statements

from muckrake.dataset import find_datasets, get_dataset_path, load_config

from .engines import get_extractor
from .engines.base import RecoverableExtractionError
from .storage import (
    Candidate,
    get_connection,
    init_db,
    load_extracted_fingerprints,
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


def text_fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def is_complex_text(value: str) -> bool:
    """Whether a name may hold several actors, or a person with their role.

    Only separators are taken as a sign: "and", "&" and brackets are nearly
    always part of a single name ("Department for Work & Pensions").
    """
    if len(value.strip()) < 20:
        return False
    return any(marker in value for marker in (",", ";", ":"))


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
    dataset_name: str | None = None,
    limit: int | None = None,
    entity_id: str | None = None,
    extractor_name: str = "delimiter",
    workers: int = 1,
) -> None:
    """Extract every distinct complex name text once.

    Approved candidates are applied by (property, text fingerprint) in every
    dataset, so a text already extracted for another dataset is skipped.
    """
    configs = find_datasets(dataset_name)
    if not configs:
        log.error("No datasets found matching '%s'", dataset_name)
        return

    extractor = get_extractor(extractor_name)

    conn = get_connection()
    init_db(conn)
    existing = load_extracted_fingerprints(
        conn, extractor=extractor_name, extractor_version=DEFAULT_EXTRACTOR_VERSION
    )

    pending: list[Candidate] = []
    cached = 0
    for config in configs:
        ds = load_config(config)
        pack_path = get_dataset_path(ds.name) / "statements.pack.csv"
        if not pack_path.exists():
            log.warning("No statements found for %s", ds.name)
            continue

        for stmt_entity_id, schema, prop, text in iter_text_statements(pack_path):
            if limit is not None and len(pending) >= limit:
                break
            if entity_id is not None and stmt_entity_id != entity_id:
                continue
            if not is_complex_text(text):
                continue

            fingerprint = text_fingerprint(text)
            if (prop, fingerprint) in existing:
                cached += 1
                continue
            existing.add((prop, fingerprint))
            pending.append(
                Candidate(
                    dataset=ds.name,
                    entity_id=stmt_entity_id,
                    schema=schema,
                    property_name=prop,
                    source_text=text,
                    fingerprint=fingerprint,
                    extractor=extractor_name,
                    extractor_version=DEFAULT_EXTRACTOR_VERSION,
                    extraction=[],
                )
            )

    log.info(
        "Extracting %s texts, %s at a time; %s repeated or already extracted.",
        len(pending),
        workers,
        cached,
    )

    async def extract(candidate: Candidate, slots: asyncio.Semaphore) -> Candidate | None:
        async with slots:
            try:
                candidate.extraction = await extractor.extract_async(candidate.source_text)
            except RecoverableExtractionError as exc:
                log.warning(
                    "Skipping extraction for %s:%s due to recoverable extractor error: %s",
                    candidate.entity_id,
                    candidate.property_name,
                    exc,
                )
                return None
        return candidate

    async def extract_all() -> tuple[int, int]:
        written = skipped = 0
        slots = asyncio.Semaphore(workers)
        tasks = [asyncio.create_task(extract(c, slots)) for c in pending]
        try:
            for done, task in enumerate(asyncio.as_completed(tasks), start=1):
                result = await task
                if result is None:
                    skipped += 1
                elif upsert_candidate(conn, result):
                    written += 1
                if done % 500 == 0:
                    log.info("Extracted %s/%s texts", done, len(pending))
        finally:
            # On a fatal error (e.g. a bad API key), stop instead of draining the queue.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return written, skipped

    written, skipped = asyncio.run(extract_all())

    conn.close()
    log.info(
        "NER extract complete. Extracted=%s, cached=%s, skipped=%s, upserted=%s.",
        len(pending) - skipped,
        cached,
        skipped,
        written,
    )
