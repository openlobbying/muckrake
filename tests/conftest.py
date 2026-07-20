from __future__ import annotations

# muckrake.settings reads the DB URIs and data/artifact paths from the
# environment *at import time* (they become module-level constants that many
# core write paths — load, release, runs — capture as default arguments). So the
# environment has to be pointed at throwaway locations before muckrake is
# imported. conftest is the earliest module pytest loads, and a plain
# ``import muckrake`` does not pull in settings, so setting the vars here — ahead
# of the import below — gives the whole suite an isolated SQLite working DB and a
# separate published DB, with no network access or repo-data side effects.
import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="muckrake-tests-"))
os.environ.pop("MUCKRAKE_DATABASE_URL", None)  # working DB falls back to the SQLite default
os.environ["MUCKRAKE_ENV_FILE"] = str(_TEST_ROOT / "missing.env")
os.environ["MUCKRAKE_DATA_PATH"] = str(_TEST_ROOT / "data")
os.environ["MUCKRAKE_ARTIFACT_PATH"] = str(_TEST_ROOT / "data" / "artifacts")
os.environ["MUCKRAKE_PUBLISHED_DATABASE_URL"] = (
    f"sqlite:///{(_TEST_ROOT / 'published.db').as_posix()}"
)
# The default SQLite working DB lives under MUCKRAKE_DATA_PATH; create it so the
# engine can open the file even in tests that touch the DB without first writing
# a dataset pack.
(_TEST_ROOT / "data").mkdir(parents=True, exist_ok=True)

import pytest  # noqa: E402
import yaml  # noqa: E402
from followthemoney.statement.serialize import PackStatementWriter  # noqa: E402

import muckrake  # noqa: E402  (must follow the env setup above)
from muckrake.dataset import Dataset, get_dataset_path  # noqa: E402

__all__ = ["muckrake"]


# A dataset spec: a schema name plus the properties to set. An explicit ``id`` may
# be supplied, otherwise a stable hashed id is derived from the schema name.
DatasetSpec = dict[str, Any]


@pytest.fixture
def make_dataset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[..., tuple[str, Path]]:
    """Write a throwaway dataset and return ``(name, pack_path)``.

    Creates a ``config.yml`` discoverable via ``MUCKRAKE_DATASET_PATHS`` and, when
    ``write_pack`` is true, a ``statements.pack.csv`` at the dataset's default
    location built from ``entities``. Pass ``write_pack=False`` to leave the pack
    absent (to exercise the missing-pack path).
    """
    roots = tmp_path / "datasets"
    roots.mkdir()
    monkeypatch.setenv("MUCKRAKE_DATASET_PATHS", str(roots))

    def _make(
        entities: list[DatasetSpec] | None = None,
        *,
        name: str | None = None,
        write_pack: bool = True,
    ) -> tuple[str, Path]:
        name = name or f"ds_{uuid.uuid4().hex[:8]}"
        config_dir = roots / name
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.yml"
        config_path.write_text(yaml.safe_dump({"name": name, "title": name, "prefix": name}))

        pack_path = get_dataset_path(name) / "statements.pack.csv"
        if write_pack:
            pack_path.parent.mkdir(parents=True, exist_ok=True)
            with pack_path.open("w") as fh:
                writer = PackStatementWriter(fh)
                dataset = Dataset(config_path, writer)
                for spec in entities or []:
                    entity = dataset.make(spec["schema"])
                    entity.id = spec.get("id") or dataset.make_id(spec["schema"])
                    for prop, values in spec["properties"].items():
                        entity.add(prop, values)
                    dataset.emit(entity)
                writer.close()

        return name, pack_path

    return _make
