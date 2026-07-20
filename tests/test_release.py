from __future__ import annotations

from pathlib import Path

import pytest

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
    name, pack_path = make_dataset(
        [{"schema": "Company", "properties": {"name": ["ACME Ltd"]}}]
    )
    _register_successful_run(name, pack_path)

    release_id = run_release_build([name])
    assert get_release(release_id).status == "built"

    run_release_publish(release_id)
    assert get_release(release_id).status == "published"

    published = _published_entities(name)
    assert len(published) == 1
    assert published[0].schema.name == "Company"
    assert published[0].get("name") == ["ACME Ltd"]


def test_release_build_fails_without_successful_run(make_dataset):
    # The config is discoverable but no successful dataset run exists.
    name, _ = make_dataset(write_pack=False)

    before = len(list_releases(limit=1000))
    with pytest.raises(ValueError, match="No successful dataset run"):
        run_release_build([name])
    # All-or-nothing: the failing precondition is checked before the release row
    # is created, so no partial release is left behind. Pinned current behaviour.
    assert len(list_releases(limit=1000)) == before


def test_release_build_is_all_or_nothing_across_datasets(make_dataset):
    ready, ready_pack = make_dataset(
        [{"schema": "Company", "properties": {"name": ["Ready Ltd"]}}]
    )
    _register_successful_run(ready, ready_pack)
    missing, _ = make_dataset(write_pack=False)

    before = len(list_releases(limit=1000))
    # One run-less dataset in the set aborts the whole build (current behaviour:
    # a release covers every discovered dataset or none). Finding for docs#38.
    with pytest.raises(ValueError, match="No successful dataset run"):
        run_release_build([ready, missing])
    assert len(list_releases(limit=1000)) == before
