from __future__ import annotations

import json
import uuid
from pathlib import Path

from muckrake.artifacts import LocalArtifactStore, file_sha256
from muckrake.db import init_database
from muckrake.runs import (
    create_dataset_run,
    finish_dataset_run,
    get_latest_successful_artifact,
    record_dataset_run_artifact,
)


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_put_bytes_round_trips_with_checksum(tmp_path: Path):
    store = LocalArtifactStore(root=tmp_path)
    stored = store.put_bytes(b"hello world", "a/b/c.txt")

    assert stored.storage_backend == "local"
    assert stored.storage_key == "a/b/c.txt"
    assert stored.absolute_path == tmp_path / "a" / "b" / "c.txt"
    assert stored.absolute_path.read_bytes() == b"hello world"
    assert stored.size_bytes == len(b"hello world")
    assert stored.sha256 == file_sha256(stored.absolute_path)


def test_put_json_is_sorted_and_round_trips(tmp_path: Path):
    store = LocalArtifactStore(root=tmp_path)
    payload = {"b": 2, "a": 1}
    stored = store.put_json(payload, "manifest.json")

    text = stored.absolute_path.read_text()
    assert json.loads(text) == payload
    # Deterministic serialisation: keys sorted so identical payloads hash equal.
    assert text.index('"a"') < text.index('"b"')
    assert store.put_json(payload, "manifest2.json").sha256 == stored.sha256


def test_put_file_copies_source(tmp_path: Path):
    source = tmp_path / "source.csv"
    source.write_text("id,name\n1,acme\n")
    store = LocalArtifactStore(root=tmp_path / "store")

    stored = store.put_file(source, "runs/1/statements.pack.csv")

    assert stored.absolute_path.read_text() == source.read_text()
    assert stored.sha256 == file_sha256(source)


def test_resolve_path_and_exists(tmp_path: Path):
    store = LocalArtifactStore(root=tmp_path)
    key = "runs/1/x.txt"
    assert store.resolve_path(key) == tmp_path / key
    assert store.exists(key) is False
    store.put_bytes(b"x", key)
    assert store.exists(key) is True


def test_put_bytes_same_key_overwrites(tmp_path: Path):
    # Pins current behaviour: LocalArtifactStore does NOT enforce immutability —
    # re-putting a storage_key overwrites in place. Artifact immutability in
    # muckrake is a convention upheld by unique per-run storage keys
    # (dataset-runs/<name>/<run_id>/...), not by the store. Finding for docs#38.
    store = LocalArtifactStore(root=tmp_path)
    first = store.put_bytes(b"one", "k")
    second = store.put_bytes(b"two", "k")
    assert first.absolute_path == second.absolute_path
    assert second.absolute_path.read_bytes() == b"two"
    assert first.sha256 != second.sha256


def test_get_latest_successful_artifact_prefers_latest_succeeded():
    dataset_name = _unique("arts")
    init_database()

    def _record(run_id: int, key: str) -> None:
        record_dataset_run_artifact(
            run_id,
            artifact_type="statements_pack",
            storage_backend="local",
            storage_key=key,
            content_type="text/csv",
            sha256="deadbeef",
            size_bytes=1,
        )

    first = create_dataset_run(dataset_name=dataset_name)
    _record(first.id, f"dataset-runs/{dataset_name}/{first.id}/statements.pack.csv")
    finish_dataset_run(first.id, "succeeded")

    second = create_dataset_run(dataset_name=dataset_name)
    second_key = f"dataset-runs/{dataset_name}/{second.id}/statements.pack.csv"
    _record(second.id, second_key)
    finish_dataset_run(second.id, "succeeded")

    # A later failed run must not shadow the latest successful artifact.
    failed = create_dataset_run(dataset_name=dataset_name)
    _record(failed.id, f"dataset-runs/{dataset_name}/{failed.id}/statements.pack.csv")
    finish_dataset_run(failed.id, "failed")

    latest = get_latest_successful_artifact(dataset_name)
    assert latest is not None
    assert latest.storage_key == second_key
