import gzip
import json
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
    """Save a reviewer's edited extraction, and record when it was edited."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET extraction_json = :extraction_json, edited_at = :now, updated_at = :now
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
    conn: Connection, size: int, pool: str = "approved", dataset_name: str | None = None
) -> int:
    """Draw up to ``size`` random candidates from one pool into the review sample.

    The pool is the automatic decision being checked: ``approved`` measures how
    many of ``AUTO_REVIEWER``'s splits are right, ``rejected`` how often it left
    a composite name whole. Only candidates decided by ``AUTO_REVIEWER`` and never
    sampled before are drawn. Each gets ``sampled_at`` and ``sampled_status`` (the
    pool), committed at once, so an interrupted review keeps its sample. Returns
    how many were drawn.
    """
    if pool not in SAMPLE_POOLS:
        raise ValueError(f"Invalid sample pool: {pool}")
    clauses = ["status = :pool", "reviewer = :reviewer", "sampled_at IS NULL"]
    params: dict[str, Any] = {"pool": pool, "reviewer": AUTO_REVIEWER, "size": size}
    if dataset_name is not None:
        clauses.append("dataset = :dataset_name")
        params["dataset_name"] = dataset_name
    ids = [
        row[0]
        for row in conn.execute(
            text(
                f"SELECT id FROM ner_candidates WHERE {' AND '.join(clauses)} "
                "ORDER BY random() LIMIT :size"
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


def sample_results(conn: Connection, dataset_name: str | None = None) -> dict[str, dict[str, int]]:
    """Per pool: candidates sampled, decided by a person, and how they were decided.

    ``approved_unedited`` counts candidates the person approved as they were, and
    ``approved_edited`` those the person edited after the candidate was sampled and
    then approved. For the ``approved`` pool, approved_unedited / decided is the
    precision of the automatic splits, and approved_edited counts the splits the
    person had to correct. For the ``rejected`` pool, approved_edited / decided is
    how often a name left whole was really composite (the person split it).
    """
    clause = "AND dataset = :dataset_name" if dataset_name is not None else ""
    edited = "edited_at IS NOT NULL AND edited_at >= sampled_at"
    rows = conn.execute(
        text(
            f"""
            SELECT sampled_status,
                   COUNT(*),
                   SUM(CASE WHEN reviewer <> :reviewer THEN 1 ELSE 0 END),
                   SUM(CASE WHEN reviewer <> :reviewer AND status = 'approved'
                            AND NOT ({edited}) THEN 1 ELSE 0 END),
                   SUM(CASE WHEN reviewer <> :reviewer AND status = 'approved'
                            AND {edited} THEN 1 ELSE 0 END)
            FROM ner_candidates
            WHERE sampled_status IS NOT NULL {clause}
            GROUP BY sampled_status
            """
        ),
        {"reviewer": AUTO_REVIEWER, "dataset_name": dataset_name},
    )
    keys = ("sampled", "decided", "approved_unedited", "approved_edited")
    results = {pool: dict.fromkeys(keys, 0) for pool in SAMPLE_POOLS}
    for pool, *counts in rows:
        results[pool] = {key: int(count or 0) for key, count in zip(keys, counts, strict=True)}
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
            if conn.execute(exists, row).first() is not None:
                present += 1
                continue
            conn.execute(insert, row)
            imported += 1
    conn.commit()
    return imported, present
