from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from muckrake.settings import ARTIFACT_PATH


@dataclass
class StoredArtifact:
    storage_backend: str
    storage_key: str
    absolute_path: Path
    sha256: str
    size_bytes: int


class LocalArtifactStore:
    storage_backend = "local"

    def __init__(self, root: Path = ARTIFACT_PATH):
        self.root = root

    def resolve_path(self, storage_key: str) -> Path:
        return self.root / storage_key

    def exists(self, storage_key: str) -> bool:
        return self.resolve_path(storage_key).exists()

    def put_file(self, source_path: Path, storage_key: str) -> StoredArtifact:
        target_path = self.resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return StoredArtifact(
            storage_backend=self.storage_backend,
            storage_key=storage_key,
            absolute_path=target_path,
            sha256=file_sha256(target_path),
            size_bytes=target_path.stat().st_size,
        )

    def put_bytes(self, data: bytes, storage_key: str) -> StoredArtifact:
        target_path = self.resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        return StoredArtifact(
            storage_backend=self.storage_backend,
            storage_key=storage_key,
            absolute_path=target_path,
            sha256=file_sha256(target_path),
            size_bytes=target_path.stat().st_size,
        )

    def put_json(self, payload: dict[str, Any], storage_key: str) -> StoredArtifact:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        return self.put_bytes(data, storage_key)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_artifact_store() -> LocalArtifactStore:
    return LocalArtifactStore()
