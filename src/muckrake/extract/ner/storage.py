import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

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


def get_connection() -> Connection:
    engine = init_database()
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


def load_cached_keys(
    conn: Connection,
    dataset: str,
    extractor: str,
    extractor_version: str,
) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        text(
            """
        SELECT entity_id, property_name, fingerprint
        FROM ner_candidates
        WHERE dataset = :dataset
          AND extractor = :extractor
          AND extractor_version = :extractor_version
        """
        ),
        {
            "dataset": dataset,
            "extractor": extractor,
            "extractor_version": extractor_version,
        },
    )
    return {(row[0], row[1], row[2]) for row in rows}


def list_candidates(
    conn: Connection,
    dataset_name: Optional[str] = None,
    status: str = "pending",
    limit: Optional[int] = None,
) -> list[RowMapping]:
    clauses = ["status = :status"]
    params: dict[str, Any] = {"status": status}
    if dataset_name is not None:
        clauses.append("dataset = :dataset_name")
        params["dataset_name"] = dataset_name

    sql = f"""
        SELECT *
        FROM ner_candidates
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at ASC, id ASC
    """
    if limit is not None:
        sql += "\nLIMIT :limit"
        params["limit"] = limit

    return list(conn.execute(text(sql), params).mappings())


def get_candidate(conn: Connection, candidate_id: int) -> Optional[RowMapping]:
    return conn.execute(
        text(
            """
            SELECT * FROM ner_candidates
            WHERE id = :candidate_id
            """
        ),
        {"candidate_id": candidate_id},
    ).mappings().first()


def update_candidate_extraction(
    conn: Connection, candidate_id: int, extraction: list[dict[str, Any]]
) -> None:
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET extraction_json = :extraction_json, updated_at = :updated_at
            WHERE id = :candidate_id
            """
        ),
        {
            "extraction_json": json.dumps(extraction, sort_keys=True),
            "updated_at": datetime.now(UTC).isoformat(),
            "candidate_id": candidate_id,
        },
    )
    conn.commit()


def review_candidate(
    conn: Connection,
    candidate_id: int,
    status: str,
    reviewer: str = "muckrake/ner-review",
) -> None:
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError(f"Invalid review status: {status}")

    reviewed_at = None if status == "pending" else datetime.now(UTC).isoformat()
    reviewer_name = None if status == "pending" else reviewer
    conn.execute(
        text(
            """
            UPDATE ner_candidates
            SET status = :status, reviewer = :reviewer, reviewed_at = :reviewed_at, updated_at = :updated_at
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
    conn.commit()
