import gzip
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from muckrake.db import init_database


@dataclass
class Candidate:
    dataset: str
    entity_id: str
    schema: str
    property_name: str
    source_text: str
    fingerprint: str
    extractor: str
    extractor_version: str
    extraction: list[dict[str, Any]]
    status: str = "pending"


def get_connection(uri: str | None = None) -> Connection:
    engine = init_database(uri=uri) if uri is not None else init_database()
    return engine.connect()


def init_db(conn: Connection) -> None:
    _ = conn


def upsert_candidate(conn: Connection, candidate: Candidate) -> bool:
    now = datetime.now(UTC).isoformat()
    params = {
        "dataset": candidate.dataset,
        "entity_id": candidate.entity_id,
        "schema": candidate.schema,
        "property_name": candidate.property_name,
        "source_text": candidate.source_text,
        "fingerprint": candidate.fingerprint,
        "extractor": candidate.extractor,
        "extractor_version": candidate.extractor_version,
        "status": candidate.status,
        "reviewer": None,
        "reviewed_at": None,
        "extraction_json": json.dumps(candidate.extraction, sort_keys=True),
        "created_at": now,
        "updated_at": now,
    }
    existing = conn.execute(
        text(
            """
            SELECT 1
            FROM ner_candidates
            WHERE dataset = :dataset
              AND entity_id = :entity_id
              AND property_name = :property_name
              AND fingerprint = :fingerprint
              AND extractor = :extractor
              AND extractor_version = :extractor_version
            """
        ),
        params,
    ).first()
    if existing is not None:
        return False

    conn.execute(
        text(
            """
            INSERT INTO ner_candidates(
                dataset, entity_id, schema, property_name, source_text, fingerprint,
                extractor, extractor_version, status, reviewer, reviewed_at,
                extraction_json, created_at, updated_at
            ) VALUES (
                :dataset, :entity_id, :schema, :property_name, :source_text, :fingerprint,
                :extractor, :extractor_version, :status, :reviewer, :reviewed_at,
                :extraction_json, :created_at, :updated_at
            )
            """
        ),
        params,
    )
    conn.commit()
    return True


def load_extracted_fingerprints(
    conn: Connection,
    extractor: str,
    extractor_version: str,
) -> set[tuple[str, str]]:
    """(property, text fingerprint) pairs already extracted, in any dataset."""
    rows = conn.execute(
        text(
            """
        SELECT DISTINCT property_name, fingerprint
        FROM ner_candidates
        WHERE extractor = :extractor
          AND extractor_version = :extractor_version
        """
        ),
        {"extractor": extractor, "extractor_version": extractor_version},
    )
    return {(row[0], row[1]) for row in rows}


def list_candidates(
    conn: Connection,
    dataset_name: str | None = None,
    status: str = "pending",
    limit: int | None = None,
) -> list[RowMapping]:
    clauses = ["status = :status"]
    params: dict[str, Any] = {"status": status}
    if dataset_name is not None:
        clauses.append("dataset = :dataset_name")
        params["dataset_name"] = dataset_name

    sql = f"""
        SELECT *
        FROM ner_candidates
        WHERE {" AND ".join(clauses)}
        ORDER BY updated_at ASC, id ASC
    """
    if limit is not None:
        sql += "\nLIMIT :limit"
        params["limit"] = limit

    return list(conn.execute(text(sql), params).mappings())


def get_candidate(conn: Connection, candidate_id: int) -> RowMapping | None:
    return (
        conn.execute(
            text(
                """
            SELECT * FROM ner_candidates
            WHERE id = :candidate_id
            """
            ),
            {"candidate_id": candidate_id},
        )
        .mappings()
        .first()
    )


def update_candidate_extraction(
    conn: Connection, candidate_id: int, extraction: list[dict[str, Any]]
) -> None:
    """Save a reviewer's edited extraction, and record when it was edited.

    The first edit also keeps the extraction as it was in
    ``original_extraction_json``; later edits never overwrite it.
    """
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET original_extraction_json = COALESCE(original_extraction_json, extraction_json),
                extraction_json = :extraction_json, edited_at = :now, updated_at = :now
            WHERE id = :candidate_id
            """
        ),
        {
            "extraction_json": json.dumps(extraction, sort_keys=True),
            "now": now,
            "candidate_id": candidate_id,
        },
    )
    conn.commit()


def review_candidate(
    conn: Connection,
    candidate_id: int,
    status: str,
    reviewer: str = "muckrake/ner-review",
    commit: bool = True,
) -> None:
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError(f"Invalid review status: {status}")

    reviewed_at = None if status == "pending" else datetime.now(UTC).isoformat()
    reviewer_name = None if status == "pending" else reviewer
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET status = :status, reviewer = :reviewer,
                reviewed_at = :reviewed_at, updated_at = :updated_at
            WHERE id = :candidate_id
            """
        ),
        {
            "status": status,
            "reviewer": reviewer_name,
            "reviewed_at": reviewed_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "candidate_id": candidate_id,
        },
    )
    if commit:
        conn.commit()


def restore_review(
    conn: Connection,
    candidate_id: int,
    status: str,
    reviewer: str | None,
    reviewed_at: str | None,
) -> None:
    """Put a candidate's decision back as it was, to undo a review decision."""
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET status = :status, reviewer = :reviewer,
                reviewed_at = :reviewed_at, updated_at = :updated_at
            WHERE id = :candidate_id
            """
        ),
        {
            "status": status,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "candidate_id": candidate_id,
        },
    )
    conn.commit()


AUTO_REVIEWER = "muckrake/auto"


def is_noop_extraction(source_text: str, extraction: list[dict[str, Any]]) -> bool:
    """True when the extraction is just the source entity again, unsplit."""
    if len(extraction) != 1:
        return False
    names = extraction[0].get("properties", {}).get("name", [])
    return names == [source_text]


def auto_review(conn: Connection, dataset_name: str | None = None) -> tuple[int, int]:
    """Decide every pending candidate without a human; returns (approved, rejected).

    Splits are approved. An extraction that only repeats the source text is
    rejected, so the original entity and its ID are kept. Candidates a human
    has already decided are not pending, so they are never changed here.
    """
    approved = rejected = 0
    for row in list_candidates(conn, dataset_name=dataset_name, status="pending"):
        extraction = json.loads(row["extraction_json"])
        if is_noop_extraction(row["source_text"], extraction):
            status = "rejected"
            rejected += 1
        else:
            status = "approved"
            approved += 1
        review_candidate(conn, row["id"], status, reviewer=AUTO_REVIEWER, commit=False)
    conn.commit()
    return approved, rejected


SAMPLE_POOLS = ("approved", "rejected")


def draw_sample(
    conn: Connection, target: int, pool: str = "approved", dataset_name: str | None = None
) -> int:
    """Bring one pool's review sample up to ``target`` candidates; returns how many were drawn.

    The pool is the automatic decision being checked: ``approved`` measures how
    many of ``AUTO_REVIEWER``'s splits are right, ``rejected`` how often it left
    a composite name whole. Only enough random candidates to reach ``target`` are
    drawn, from those decided by ``AUTO_REVIEWER`` and never sampled before, so
    running it again with the same target draws nothing. Each drawn candidate
    gets ``sampled_at`` and ``sampled_status`` (the pool), committed at once, so an
    interrupted review keeps its sample.
    """
    if pool not in SAMPLE_POOLS:
        raise ValueError(f"Invalid sample pool: {pool}")
    scope = ""
    params: dict[str, Any] = {"pool": pool, "reviewer": AUTO_REVIEWER}
    if dataset_name is not None:
        scope = " AND dataset = :dataset_name"
        params["dataset_name"] = dataset_name
    sampled = conn.execute(
        text(f"SELECT COUNT(*) FROM ner_candidates WHERE sampled_status = :pool{scope}"),
        params,
    ).scalar_one()
    params["size"] = max(0, target - sampled)
    if params["size"] == 0:
        return 0
    ids = [
        row[0]
        for row in conn.execute(
            text(
                "SELECT id FROM ner_candidates WHERE status = :pool AND reviewer = :reviewer "
                f"AND sampled_at IS NULL{scope} ORDER BY random() LIMIT :size"
            ),
            params,
        )
    ]
    sampled_at = datetime.now(UTC).isoformat()
    for candidate_id in ids:
        conn.execute(
            text(
                "UPDATE ner_candidates SET sampled_at = :sampled_at, sampled_status = :pool "
                "WHERE id = :candidate_id"
            ),
            {"sampled_at": sampled_at, "pool": pool, "candidate_id": candidate_id},
        )
    conn.commit()
    return len(ids)


def list_sample_awaiting_review(
    conn: Connection, pool: str = "approved", dataset_name: str | None = None
) -> list[RowMapping]:
    """A pool's sampled candidates no person has decided yet (still ``AUTO_REVIEWER``'s)."""
    clauses = ["sampled_status = :pool", "reviewer = :reviewer"]
    params: dict[str, Any] = {"pool": pool, "reviewer": AUTO_REVIEWER}
    if dataset_name is not None:
        clauses.append("dataset = :dataset_name")
        params["dataset_name"] = dataset_name
    sql = f"SELECT * FROM ner_candidates WHERE {' AND '.join(clauses)} ORDER BY sampled_at, id"
    return list(conn.execute(text(sql), params).mappings())


def entity_forms(extraction: list[dict[str, Any]]) -> Counter[tuple[Any, ...]]:
    """Each extracted entity as a comparable form: its schema and properties.

    ``key`` and the order of entities and values are ignored. A ``$ref:<key>``
    value is compared as the schema and first name of the entity it points to,
    since keys are local to one extraction and a reviewer may rename them.
    """
    targets = {
        entity.get("key"): (
            entity.get("schema"),
            (entity.get("properties", {}).get("name") or [""])[0],
        )
        for entity in extraction
        if entity.get("key")
    }

    def value(raw: Any) -> Any:
        if isinstance(raw, str) and raw.startswith("$ref:"):
            return ("ref", *targets.get(raw[5:], ("?", "?")))
        return raw

    forms: Counter[tuple[Any, ...]] = Counter()
    for entity in extraction:
        props = entity.get("properties", {})
        forms[
            (
                entity.get("schema"),
                tuple(
                    sorted((p, tuple(sorted(map(value, vs), key=str))) for p, vs in props.items())
                ),
            )
        ] += 1
    return forms


def compare_extractions(
    original: list[dict[str, Any]], final: list[dict[str, Any]]
) -> tuple[int, int, int]:
    """(kept, removed, added): original entities left unchanged, and the reviewer's changes."""
    before, after = entity_forms(original), entity_forms(final)
    kept = sum((before & after).values())
    return kept, sum(before.values()) - kept, sum(after.values()) - kept


def sample_results(conn: Connection, dataset_name: str | None = None) -> dict[str, dict[str, Any]]:
    """Per pool: how the sampled candidates were decided, per split and per entity.

    Per split: ``sampled``, ``decided`` by a person, ``approved_unedited`` and
    ``approved_edited`` (edited after the candidate was sampled, then approved).
    For the ``approved`` pool, approved_unedited / decided is the precision of the
    automatic splits; for the ``rejected`` pool, approved_edited / decided is how
    often a name left whole was really composite.

    Per entity, under ``entities``, relative to what the automatic decision
    produced: ``checked`` entities, ``kept`` unchanged, ``removed`` and ``added``
    by the reviewer. An unedited approval keeps every entity; an edited one is
    compared with the extraction before its first edit. A person's rejection
    removes every entity of an auto-approved split, and keeps the single entity of
    an auto-rejected one. Candidates edited before originals were kept are left
    out of the entity counts and counted in ``edited_without_original``.
    """
    clause = "AND dataset = :dataset_name" if dataset_name is not None else ""
    rows = conn.execute(
        text(
            f"""
            SELECT sampled_status, status, reviewer, sampled_at, edited_at,
                   extraction_json, original_extraction_json
            FROM ner_candidates
            WHERE sampled_status IS NOT NULL {clause}
            """
        ),
        {"dataset_name": dataset_name},
    ).mappings()
    results: dict[str, dict[str, Any]] = {
        pool: {
            "sampled": 0,
            "decided": 0,
            "approved_unedited": 0,
            "approved_edited": 0,
            "edited_without_original": 0,
            "entities": {"checked": 0, "kept": 0, "removed": 0, "added": 0},
        }
        for pool in SAMPLE_POOLS
    }
    for row in rows:
        counts = results[row["sampled_status"]]
        counts["sampled"] += 1
        if row["reviewer"] == AUTO_REVIEWER:
            continue
        counts["decided"] += 1
        edited = row["edited_at"] is not None and row["edited_at"] >= row["sampled_at"]
        approved = row["status"] == "approved"
        if approved:
            counts["approved_edited" if edited else "approved_unedited"] += 1
        if edited and row["original_extraction_json"] is None:
            counts["edited_without_original"] += 1
            continue
        final = json.loads(row["extraction_json"])
        original = json.loads(row["original_extraction_json"]) if edited else final
        entities = counts["entities"]
        entities["checked"] += len(original)
        if approved:
            kept, removed, added = compare_extractions(original, final)
        elif row["sampled_status"] == "approved":
            kept, removed, added = 0, len(original), 0
        else:
            kept, removed, added = len(original), 0, 0
        entities["kept"] += kept
        entities["removed"] += removed
        entities["added"] += added
    return results


# Everything but the local row id, so an export can be imported into any database.
EXPORT_COLUMNS = (
    "dataset",
    "entity_id",
    "schema",
    "property_name",
    "source_text",
    "fingerprint",
    "extractor",
    "extractor_version",
    "status",
    "reviewer",
    "reviewed_at",
    "sampled_at",
    "sampled_status",
    "edited_at",
    "original_extraction_json",
    "extraction_json",
    "created_at",
    "updated_at",
)
KEY_COLUMNS = (
    "dataset",
    "entity_id",
    "property_name",
    "fingerprint",
    "extractor",
    "extractor_version",
)


def _open(path: Path, write: bool) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "wt" if write else "rt", encoding="utf-8")
    return path.open("w" if write else "r", encoding="utf-8")


def export_candidates(conn: Connection, path: Path) -> int:
    """Write every candidate, with its review decision, as JSON lines."""
    rows = conn.execute(
        text(f"SELECT {', '.join(EXPORT_COLUMNS)} FROM ner_candidates ORDER BY id")
    ).mappings()
    count = 0
    with _open(path, write=True) as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def import_candidates(conn: Connection, path: Path) -> tuple[int, int]:
    """Add candidates from an export; returns (imported, already_present).

    A candidate already in the database is left as it is, so local review
    decisions and samples are never overwritten. Exports made before
    the sample and edit columns existed import with them unset.
    """
    exists = text(
        "SELECT 1 FROM ner_candidates WHERE " + " AND ".join(f"{c} = :{c}" for c in KEY_COLUMNS)
    )
    insert = text(
        f"INSERT INTO ner_candidates({', '.join(EXPORT_COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in EXPORT_COLUMNS)})"
    )
    imported = present = 0
    with _open(path, write=False) as fh:
        for line in fh:
            row = json.loads(line)
            row.setdefault("sampled_at", None)
            row.setdefault("sampled_status", None)
            row.setdefault("edited_at", None)
            row.setdefault("original_extraction_json", None)
            if conn.execute(exists, row).first() is not None:
                present += 1
                continue
            conn.execute(insert, row)
            imported += 1
    conn.commit()
    return imported, present
