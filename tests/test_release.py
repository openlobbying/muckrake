from __future__ import annotations

from pathlib import Path

import pytest
from nomenklatura.db import get_engine
from sqlalchemy import inspect

from muckrake import settings
from muckrake.artifacts import get_artifact_store
from muckrake.db import init_database
from muckrake.release import (
    get_release,
    list_releases,
    run_release_build,
    run_release_publish,
)
from muckrake.runs import (
    create_dataset_run,
    finish_dataset_run,
    record_dataset_run_artifact,
)
from muckrake.store import get_sql_store


def _register_successful_run(name: str, pack_path: Path) -> int:
    """Record a succeeded crawl run + statements artifact for a built pack."""
    init_database()
    run = create_dataset_run(dataset_name=name)
    stored = get_artifact_store().put_file(
        pack_path, f"dataset-runs/{name}/{run.id}/statements.pack.csv"
    )
    record_dataset_run_artifact(
        run.id,
        artifact_type="statements_pack",
        storage_backend=stored.storage_backend,
        storage_key=stored.storage_key,
        content_type="text/csv",
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
    )
    finish_dataset_run(run.id, "succeeded")
    return run.id


def _published_entities(name: str):
    store = get_sql_store([name], uri=settings.PUBLISHED_SQL_URI)
    return list(store.view(store.dataset).entities())


def test_release_build_then_publish_copies_statements(make_dataset):
    name, pack_path = make_dataset([{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}])
    _register_successful_run(name, pack_path)

    release_id = run_release_build([name])
    assert get_release(release_id).status == "built"

    run_release_publish(release_id)
    assert get_release(release_id).status == "published"

    published = _published_entities(name)
    assert len(published) == 1
    assert published[0].schema.name == "Company"
    assert published[0].get("name") == ["ACME Ltd"]


def test_publish_indexes_references_and_identifiers(make_dataset):
    name, pack_path = make_dataset([{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}])
    _register_successful_run(name, pack_path)
    run_release_publish(run_release_build([name]))

    # Entity references are indexed by nomenklatura, identifiers by muckrake.
    # (Which index SQLite's planner picks for a tiny table varies by version, so
    # check that they exist rather than that a query uses them.)
    indexes = inspect(get_engine(settings.PUBLISHED_SQL_URI)).get_indexes("statement")
    names = {index["name"] for index in indexes}
    assert {"ix_statement_value_entity", "ix_statement_value_identifier"} <= names


def test_release_build_fails_with_nothing_to_build(make_dataset):
    # A single requested dataset with no successful run: raising is the correct
    # contract (there is nothing to build), and the precondition is checked
    # before the release row is created, so no partial release is left behind.
    # This is a legitimate contract, not a pin — kept as a plain assertion.
    name, _ = make_dataset(write_pack=False)

    before = len(list_releases(limit=1000))
    with pytest.raises(ValueError, match="No successful dataset run"):
        run_release_build([name])
    assert len(list_releases(limit=1000)) == before


@pytest.mark.xfail(
    reason=(
        "muckrake#30 (proposed): release-build should build from the datasets that "
        "succeeded and exclude/record run-less ones, rather than aborting the whole "
        "release. If #30 decides all-or-nothing is the intended contract, replace this "
        "with a plain assertion of that behaviour."
    ),
    strict=True,
)
def test_release_build_includes_successful_datasets(make_dataset):
    # Desired: one run-less dataset in the set must not block a release of the
    # datasets that did succeed. Today run_release_build aborts the whole build.
    ready, ready_pack = make_dataset([{"schema": "Company", "properties": {"name": ["Ready Ltd"]}}])
    _register_successful_run(ready, ready_pack)
    missing, _ = make_dataset(write_pack=False)

    before = len(list_releases(limit=1000))
    release_id = run_release_build([ready, missing])
    assert release_id is not None
    assert len(list_releases(limit=1000)) == before + 1


def test_failed_publish_keeps_previous_release(make_dataset, monkeypatch):
    import muckrake.release as release_module
    from muckrake.store import MuckrakeSQLWriter

    name, pack_path = make_dataset(
        [
            {"schema": "Company", "properties": {"name": ["ACME Ltd"]}},
            {"schema": "Person", "properties": {"name": ["Jane Doe"]}},
        ]
    )
    _register_successful_run(name, pack_path)
    release_id = run_release_build([name])
    run_release_publish(release_id)
    assert len(_published_entities(name)) == 2

    monkeypatch.setattr(MuckrakeSQLWriter, "BATCH_STATEMENTS", 1)
    real = release_module.read_pack_statements

    def broken(fh):
        for stmt in real(fh):
            yield stmt
            raise RuntimeError("publish interrupted")

    monkeypatch.setattr(release_module, "read_pack_statements", broken)
    with pytest.raises(RuntimeError, match="publish interrupted"):
        run_release_publish(release_id)

    # The published DB still serves the previous release in full.
    assert len(_published_entities(name)) == 2


def test_artifacts_over_2_gib_are_recorded():
    """Release packs grow past 2 GiB, which overflowed a 32-bit size_bytes column."""
    init_database()
    run = create_dataset_run(dataset_name="big")
    record_dataset_run_artifact(
        run.id,
        artifact_type="statements_pack",
        storage_backend="local",
        storage_key="dataset-runs/big/1/statements.pack.csv",
        content_type="text/csv",
        sha256="0" * 64,
        size_bytes=3_082_170_143,
    )
    finish_dataset_run(run.id, "succeeded")
