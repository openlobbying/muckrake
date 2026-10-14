from __future__ import annotations

import pytest
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


def _fail_after_first_statement(real):
    def broken(*args, **kwargs):
        for stmt in real(*args, **kwargs):
            yield stmt
            raise RuntimeError("load interrupted")

    return broken


def test_failed_load_keeps_previously_loaded_statements(make_dataset, monkeypatch):
    import muckrake.load as load_module
    from muckrake.store import MuckrakeSQLWriter

    name, _ = make_dataset(
        [
            {"schema": "Company", "properties": {"name": ["ACME Ltd"]}},
            {"schema": "Person", "properties": {"name": ["Jane Doe"]}},
        ]
    )
    run_load(name)
    before = _statement_count(name)

    # Batches of one, so the interrupted load really has written rows to roll back.
    monkeypatch.setattr(MuckrakeSQLWriter, "BATCH_STATEMENTS", 1)
    monkeypatch.setattr(
        load_module,
        "iter_dataset_statements",
        _fail_after_first_statement(load_module.iter_dataset_statements),
    )
    with pytest.raises(RuntimeError, match="load interrupted"):
        run_load(name)

    assert _statement_count(name) == before
    assert sorted(e.get("name")[0] for e in _entities(name)) == ["ACME Ltd", "Jane Doe"]


# The two tests below assert the DESIRED behaviour and are expected to fail
# until muckrake#29 lands. strict=True means they flip the suite red the moment
# the behaviour is fixed, prompting removal of the marker — so they can never
# silently protect the current silent-no-op. Today run_load returns None without
# raising; a missing pack usually means an upstream crawl produced no artifact,
# which should surface as a failure rather than be skipped.


@pytest.mark.xfail(
    reason="muckrake#29: a missing statements pack should raise, not silently no-op",
    strict=True,
)
def test_load_missing_pack_raises(make_dataset):
    name, pack_path = make_dataset(write_pack=False)
    assert not pack_path.exists()

    with pytest.raises(Exception):  # noqa: B017 — exact type deferred to the muckrake#29 fix
        run_load(name)


@pytest.mark.xfail(
    reason="muckrake#29: loading an unknown dataset should raise, not silently return None",
    strict=True,
)
def test_load_unknown_dataset_raises():
    with pytest.raises(Exception):  # noqa: B017 — exact type deferred to the muckrake#29 fix
        run_load("dataset-that-does-not-exist")
