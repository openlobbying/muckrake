from __future__ import annotations

from muckrake.db import get_database_dialect, init_database
from muckrake.extract.ner.storage import Candidate, get_connection, list_candidates, upsert_candidate
from muckrake.search import postgres_search_ready, refresh_search_index


def test_init_database_supports_sqlite(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", f"sqlite:///{database_path}")

    engine = init_database(f"sqlite:///{database_path}")

    assert engine.dialect.name == "sqlite"
    assert get_database_dialect(f"sqlite:///{database_path}") == "sqlite"


def test_ner_candidate_storage_works_with_sqlite(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    uri = f"sqlite:///{database_path}"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", uri)

    conn = get_connection(uri)
    try:
        created = upsert_candidate(
            conn,
            Candidate(
                dataset="test",
                entity_id="entity-1",
                schema="Person",
                property_name="name",
                source_text="Alice Example",
                fingerprint="alice-example",
                extractor="test-extractor",
                extractor_version="1",
                extraction=[{"schema": "Person", "properties": {"name": ["Alice Example"]}}],
            ),
        )
        rows = list_candidates(conn, dataset_name="test")
    finally:
        conn.close()

    assert created is True
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "entity-1"


def test_search_refresh_is_noop_for_sqlite(monkeypatch, tmp_path):
    database_path = tmp_path / "muckrake.db"
    uri = f"sqlite:///{database_path}"
    monkeypatch.setenv("MUCKRAKE_DATABASE_URL", uri)
    monkeypatch.setenv("MUCKRAKE_PUBLISHED_DATABASE_URL", uri)

    init_database(uri)
    refresh_search_index(uri)

    assert postgres_search_ready(uri) is False
