"""Publishing into Postgres, which swaps in new tables built with COPY.

Runs only when MUCKRAKE_TEST_POSTGRES_URL points at a throwaway database (CI
provides one); the rest of the suite uses SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from followthemoney.statement.serialize import PackStatementWriter
from nomenklatura.db import get_engine
from sqlalchemy import text
from test_release import _register_successful_run

import muckrake.release as release_module
from muckrake import settings
from muckrake.dataset import Dataset, get_dataset_path
from muckrake.release import run_release_build, run_release_publish
from muckrake.store import get_sql_store

POSTGRES_URL = settings._normalize_database_url(os.environ.get("MUCKRAKE_TEST_POSTGRES_URL"))
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUCKRAKE_TEST_POSTGRES_URL not set")


@pytest.fixture
def published_postgres(monkeypatch):
    assert POSTGRES_URL is not None
    with get_engine(POSTGRES_URL).begin() as conn:
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS entity_search"))
        conn.execute(text("DROP TABLE IF EXISTS statement, statement_new, resolver CASCADE"))
    monkeypatch.setattr(settings, "PUBLISHED_SQL_URI", POSTGRES_URL)
    monkeypatch.setattr(release_module, "PUBLISHED_SQL_URI", POSTGRES_URL)
    return POSTGRES_URL


def _query(sql: str) -> list:
    assert POSTGRES_URL is not None
    with get_engine(POSTGRES_URL).connect() as conn:
        return list(conn.execute(text(sql)))


def _entities(name: str):
    store = get_sql_store([name], uri=POSTGRES_URL)
    return {e.id: e for e in store.view(store.dataset).entities()}


def _publish(name: str, pack_path: Path) -> None:
    _register_successful_run(name, pack_path)
    run_release_publish(run_release_build([name]))


def test_publish_swaps_in_statements_and_search_view(make_dataset, published_postgres):
    name, pack_path = make_dataset([{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}])
    _publish(name, pack_path)
    # Publish again, so the swap runs over existing tables and index names.
    _publish(name, pack_path)

    assert [e.get("name") for e in _entities(name).values()] == [["ACME Ltd"]]
    assert _query("SELECT display_name FROM entity_search") == [("ACME Ltd",)]
    leftovers = _query(
        "SELECT indexname FROM pg_indexes WHERE indexname LIKE '%\\_new%' "
        "UNION SELECT relname FROM pg_class WHERE relname LIKE '%\\_new'"
    )
    assert leftovers == []
    assert ("statement_pkey",) in _query("SELECT indexname FROM pg_indexes")


def test_repeated_statements_resolve_like_an_upsert(make_dataset, published_postgres):
    # The same entity emitted twice with a different schema gives two statements
    # with the same id. As with the row-by-row upsert, the last one wins.
    name, _ = make_dataset(write_pack=False)
    pack_path = get_dataset_path(name) / "statements.pack.csv"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = Path(os.environ["MUCKRAKE_DATASET_PATHS"]) / name / "config.yml"
    with pack_path.open("w") as fh:
        writer = PackStatementWriter(fh)
        dataset = Dataset(config_path, writer)
        for schema in ("LegalEntity", "Organization"):
            entity = dataset.make(schema)
            entity.id = "results-uk"
            entity.add("name", "Results UK")
            dataset.emit(entity)
        writer.close()

    _publish(name, pack_path)

    rows = _query("SELECT schema FROM statement WHERE prop = 'name'")
    assert rows == [("Organization",)]


def test_failed_publish_keeps_previous_release(make_dataset, published_postgres, monkeypatch):
    name, pack_path = make_dataset(
        [
            {"schema": "Company", "properties": {"name": ["ACME Ltd"]}},
            {"schema": "Person", "properties": {"name": ["Jane Doe"]}},
        ]
    )
    _publish(name, pack_path)
    release_id = run_release_build([name])

    real = release_module.read_pack_statements

    def broken(fh):
        for stmt in real(fh):
            yield stmt
            raise RuntimeError("publish interrupted")

    monkeypatch.setattr(release_module, "read_pack_statements", broken)
    with pytest.raises(RuntimeError, match="publish interrupted"):
        run_release_publish(release_id)

    assert len(_entities(name)) == 2
    assert _query("SELECT to_regclass('statement_new')") == [(None,)]
