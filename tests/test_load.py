from __future__ import annotations

from sqlalchemy import func, select

from muckrake.load import run_load
from muckrake.store import get_sql_store


def _entities(dataset_name: str):
    store = get_sql_store([dataset_name])
    return list(store.view(store.dataset).entities())


def _statement_count(dataset_name: str) -> int:
    store = get_sql_store([dataset_name])
    with store.engine.connect() as conn:
        return conn.execute(
            select(func.count())
            .select_from(store.table)
            .where(store.table.c.dataset == dataset_name)
        ).scalar_one()


def test_load_materialises_entities(make_dataset):
    name, _ = make_dataset([{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}])

    run_load(name)

    entities = _entities(name)
    assert len(entities) == 1
    assert entities[0].schema.name == "Company"
    assert entities[0].get("name") == ["ACME Ltd"]


def test_reload_is_idempotent(make_dataset):
    name, _ = make_dataset([{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}])

    run_load(name)
    first_count = _statement_count(name)
    run_load(name)
    second_count = _statement_count(name)

    # run_load clears the dataset before reloading, so a re-load is a no-op:
    # neither entities nor statements are duplicated.
    assert first_count == second_count
    entities = _entities(name)
    assert len(entities) == 1
    assert entities[0].get("name") == ["ACME Ltd"]


def test_load_missing_pack_is_silent_noop(make_dataset):
    # The config is discoverable but no statements.pack.csv exists. Pins current
    # behaviour: run_load logs a warning and returns normally (no error, nothing
    # materialised). Known finding (docs#38) — a missing pack, which can mean an
    # upstream crawl produced no artifact, is silently skipped rather than
    # surfaced as a failure.
    name, pack_path = make_dataset(write_pack=False)
    assert not pack_path.exists()

    assert run_load(name) is None
    assert _entities(name) == []


def test_load_unknown_dataset_is_silent_noop():
    # No config matches: run_load logs an error and returns None without raising.
    # Pinned as current behaviour (docs#38).
    assert run_load("dataset-that-does-not-exist") is None
