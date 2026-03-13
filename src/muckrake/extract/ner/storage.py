import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from muckrake.settings import SQL_PATH


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


def get_connection(path: Path = SQL_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ner_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            schema TEXT NOT NULL,
            property_name TEXT NOT NULL,
            source_text TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            extractor TEXT NOT NULL,
            extractor_version TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewer TEXT,
            reviewed_at TEXT,
            extraction_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(dataset, entity_id, property_name, fingerprint, extractor, extractor_version)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ner_candidates_lookup
        ON ner_candidates(dataset, status, updated_at)
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ner_candidates)")}
    if "reviewer" not in cols:
        conn.execute("ALTER TABLE ner_candidates ADD COLUMN reviewer TEXT")
    if "reviewed_at" not in cols:
        conn.execute("ALTER TABLE ner_candidates ADD COLUMN reviewed_at TEXT")
    conn.commit()


def upsert_candidate(conn: sqlite3.Connection, candidate: Candidate) -> bool:
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        """
        INSERT INTO ner_candidates(
            dataset, entity_id, schema, property_name, source_text, fingerprint,
            extractor, extractor_version, status, reviewer, reviewed_at,
            extraction_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset, entity_id, property_name, fingerprint, extractor, extractor_version)
        DO NOTHING
        """,
        (
            candidate.dataset,
            candidate.entity_id,
            candidate.schema,
            candidate.property_name,
            candidate.source_text,
            candidate.fingerprint,
            candidate.extractor,
            candidate.extractor_version,
            candidate.status,
            None,
            None,
            json.dumps(candidate.extraction, sort_keys=True),
            now,
            now,
        ),
    )
    conn.commit()
    return cur.rowcount == 1


def load_cached_keys(
    conn: sqlite3.Connection,
    dataset: str,
    extractor: str,
    extractor_version: str,
) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        """
        SELECT entity_id, property_name, fingerprint
        FROM ner_candidates
        WHERE dataset = ?
          AND extractor = ?
          AND extractor_version = ?
        """,
        (dataset, extractor, extractor_version),
    )
    return {(row[0], row[1], row[2]) for row in rows}


def list_candidates(
    conn: sqlite3.Connection,
    dataset_name: Optional[str] = None,
    status: str = "pending",
    limit: Optional[int] = None,
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    if dataset_name is None and limit is None:
        cur = conn.execute(
            """
            SELECT * FROM ner_candidates
            WHERE status = ?
            ORDER BY updated_at ASC, id ASC
            """,
            (status,),
        )
    elif dataset_name is None:
        cur = conn.execute(
            """
            SELECT * FROM ner_candidates
            WHERE status = ?
            ORDER BY updated_at ASC, id ASC
            LIMIT ?
            """,
            (status, limit),
        )
    elif limit is None:
        cur = conn.execute(
            """
            SELECT * FROM ner_candidates
            WHERE dataset = ? AND status = ?
            ORDER BY updated_at ASC, id ASC
            """,
            (dataset_name, status),
        )
    else:
        cur = conn.execute(
            """
            SELECT * FROM ner_candidates
            WHERE dataset = ? AND status = ?
            ORDER BY updated_at ASC, id ASC
            LIMIT ?
            """,
            (dataset_name, status, limit),
        )
    return list(cur)


def get_candidate(conn: sqlite3.Connection, candidate_id: int) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT * FROM ner_candidates
        WHERE id = ?
        """,
        (candidate_id,),
    )
    return cur.fetchone()


def update_candidate_extraction(
    conn: sqlite3.Connection, candidate_id: int, extraction: list[dict[str, Any]]
) -> None:
    conn.execute(
        """
        UPDATE ner_candidates
        SET extraction_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            json.dumps(extraction, sort_keys=True),
            datetime.now(UTC).isoformat(),
            candidate_id,
        ),
    )
    conn.commit()


def review_candidate(
    conn: sqlite3.Connection,
    candidate_id: int,
    status: str,
    reviewer: str = "muckrake/ner-review",
) -> None:
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError(f"Invalid review status: {status}")

    reviewed_at = None if status == "pending" else datetime.now(UTC).isoformat()
    reviewer_name = None if status == "pending" else reviewer
    conn.execute(
        """
        UPDATE ner_candidates
        SET status = ?, reviewer = ?, reviewed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            reviewer_name,
            reviewed_at,
            datetime.now(UTC).isoformat(),
            candidate_id,
        ),
    )
    conn.commit()
