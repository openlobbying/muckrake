from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from followthemoney.statement.serialize import PackStatementWriter, read_pack_statements
from nomenklatura.db import get_engine
from nomenklatura.resolver import Resolver
from sqlalchemy import delete, desc, select, update
from sqlalchemy import MetaData

from muckrake.artifacts import get_artifact_store
from muckrake.dataset import find_datasets, load_config
from muckrake.db import (
    get_ner_candidates_table,
    get_release_artifacts_table,
    get_release_inputs_table,
    get_releases_table,
    init_database,
    init_published_database,
    refresh_postgres_search,
)
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.runs import (
    detect_code_version,
    get_latest_successful_run,
    resolve_dataset_pack,
    utc_now_iso,
)
from muckrake.settings import PUBLISHED_SQL_URI, SQL_URI
from muckrake.store import get_sql_store

log = logging.getLogger(__name__)


@dataclass
class Release:
    id: int
    status: str
    triggered_by: str | None
    code_version: str | None
    notes: str | None
    error_message: str | None
    created_at: str
    finished_at: str | None
    published_at: str | None


def create_release(
    *,
    triggered_by: str = "muckrake/release-build",
    notes: str | None = None,
) -> Release:
    engine = init_database()
    table = get_releases_table()
    now = utc_now_iso()
    with engine.begin() as conn:
        result = conn.execute(
            table.insert().values(
                status="building",
                triggered_by=triggered_by,
                code_version=detect_code_version(),
                notes=notes,
                error_message=None,
                created_at=now,
                finished_at=None,
                published_at=None,
            )
        )
        release_id = result.inserted_primary_key[0]
        row = (
            conn.execute(select(table).where(table.c.id == release_id)).mappings().one()
        )
    return Release(**row)


def update_release(
    release_id: int,
    *,
    status: str,
    error_message: str | None = None,
    published: bool = False,
) -> None:
    engine = init_database()
    table = get_releases_table()
    values: dict[str, Any] = {
        "status": status,
        "error_message": error_message,
        "finished_at": utc_now_iso(),
    }
    if published:
        values["published_at"] = utc_now_iso()
    with engine.begin() as conn:
        conn.execute(update(table).where(table.c.id == release_id).values(**values))
        if published:
            conn.execute(
                update(table)
                .where(table.c.id != release_id)
                .where(table.c.status == "published")
                .values(status="superseded")
            )


def get_release(release_id: int) -> Release | None:
    engine = init_database()
    table = get_releases_table()
    with engine.begin() as conn:
        row = (
            conn.execute(select(table).where(table.c.id == release_id))
            .mappings()
            .first()
        )
    if row is None:
        return None
    return Release(**row)


def list_releases(limit: int = 20) -> list[Release]:
    engine = init_database()
    table = get_releases_table()
    with engine.begin() as conn:
        rows = (
            conn.execute(select(table).order_by(desc(table.c.id)).limit(limit))
            .mappings()
            .all()
        )
    return [Release(**row) for row in rows]


def add_release_input(release_id: int, dataset_run_id: int, dataset_name: str) -> None:
    engine = init_database()
    table = get_release_inputs_table()
    with engine.begin() as conn:
        conn.execute(
            table.insert().values(
                release_id=release_id,
                dataset_run_id=dataset_run_id,
                dataset_name=dataset_name,
            )
        )


def get_release_inputs(release_id: int) -> list[dict[str, Any]]:
    engine = init_database()
    table = get_release_inputs_table()
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(table)
                .where(table.c.release_id == release_id)
                .order_by(table.c.dataset_name.asc())
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def add_release_artifact(
    release_id: int,
    *,
    artifact_type: str,
    storage_backend: str,
    storage_key: str,
    content_type: str | None,
    sha256: str,
    size_bytes: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    engine = init_database()
    table = get_release_artifacts_table()
    with engine.begin() as conn:
        conn.execute(
            table.insert().values(
                release_id=release_id,
                artifact_type=artifact_type,
                storage_backend=storage_backend,
                storage_key=storage_key,
                content_type=content_type,
                sha256=sha256,
                size_bytes=size_bytes,
                metadata_json=json.dumps(metadata, sort_keys=True)
                if metadata
                else None,
                created_at=utc_now_iso(),
            )
        )


def get_release_artifact(
    release_id: int,
    artifact_type: str = "statements_pack",
) -> dict[str, Any] | None:
    engine = init_database()
    table = get_release_artifacts_table()
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(table)
                .where(table.c.release_id == release_id)
                .where(table.c.artifact_type == artifact_type)
                .order_by(desc(table.c.id))
            )
            .mappings()
            .first()
        )
    if row is None:
        return None
    return dict(row)


def run_release_build(
    dataset_names: Optional[Iterable[str]] = None,
    notes: str | None = None,
) -> int:
    selected = _resolve_dataset_names(dataset_names)
    dataset_runs: list[tuple[str, int, Path]] = []
    for dataset_name in selected:
        run = get_latest_successful_run(dataset_name)
        if run is None:
            raise ValueError(f"No successful dataset run found for {dataset_name}")
        run_id, path = resolve_dataset_pack(dataset_name, run.id)
        dataset_runs.append((dataset_name, run_id, path))

    release = create_release(notes=notes)
    store = get_artifact_store()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"muckrake-release-{release.id}-"))
    temp_pack = temp_dir / "statements.pack.csv"
    temp_resolver = temp_dir / "resolver.json"
    temp_ner = temp_dir / "ner-candidates.json"
    storage_prefix = f"releases/{release.id}"

    try:
        with open(temp_pack, "w") as fh:
            writer = PackStatementWriter(fh)
            for dataset_name, run_id, pack_path in dataset_runs:
                add_release_input(release.id, run_id, dataset_name)
                for stmt in iter_dataset_statements(dataset_name, pack_path):
                    writer.write(stmt)
            writer.close()

        stored_pack = store.put_file(temp_pack, f"{storage_prefix}/statements.pack.csv")
        add_release_artifact(
            release.id,
            artifact_type="statements_pack",
            storage_backend=stored_pack.storage_backend,
            storage_key=stored_pack.storage_key,
            content_type="text/csv",
            sha256=stored_pack.sha256,
            size_bytes=stored_pack.size_bytes,
            metadata={"dataset_names": [name for name, _, _ in dataset_runs]},
        )

        _write_resolver_snapshot(temp_resolver)
        stored_resolver = store.put_file(
            temp_resolver, f"{storage_prefix}/resolver.json"
        )
        add_release_artifact(
            release.id,
            artifact_type="resolver_snapshot",
            storage_backend=stored_resolver.storage_backend,
            storage_key=stored_resolver.storage_key,
            content_type="application/json",
            sha256=stored_resolver.sha256,
            size_bytes=stored_resolver.size_bytes,
        )

        _write_approved_ner_snapshot(temp_ner)
        stored_ner = store.put_file(temp_ner, f"{storage_prefix}/ner-candidates.json")
        add_release_artifact(
            release.id,
            artifact_type="ner_candidates_snapshot",
            storage_backend=stored_ner.storage_backend,
            storage_key=stored_ner.storage_key,
            content_type="application/json",
            sha256=stored_ner.sha256,
            size_bytes=stored_ner.size_bytes,
        )

        manifest = {
            "release_id": release.id,
            "status": "built",
            "dataset_runs": [
                {"dataset_name": name, "dataset_run_id": run_id}
                for name, run_id, _ in dataset_runs
            ],
            "artifacts": [
                {
                    "artifact_type": "statements_pack",
                    "storage_key": stored_pack.storage_key,
                    "sha256": stored_pack.sha256,
                    "size_bytes": stored_pack.size_bytes,
                },
                {
                    "artifact_type": "resolver_snapshot",
                    "storage_key": stored_resolver.storage_key,
                    "sha256": stored_resolver.sha256,
                    "size_bytes": stored_resolver.size_bytes,
                },
                {
                    "artifact_type": "ner_candidates_snapshot",
                    "storage_key": stored_ner.storage_key,
                    "sha256": stored_ner.sha256,
                    "size_bytes": stored_ner.size_bytes,
                },
            ],
        }
        stored_manifest = store.put_json(manifest, f"{storage_prefix}/manifest.json")
        add_release_artifact(
            release.id,
            artifact_type="manifest",
            storage_backend=stored_manifest.storage_backend,
            storage_key=stored_manifest.storage_key,
            content_type="application/json",
            sha256=stored_manifest.sha256,
            size_bytes=stored_manifest.size_bytes,
        )
        update_release(release.id, status="built")
    except Exception as exc:
        update_release(release.id, status="failed", error_message=str(exc))
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    log.info("Release built: release_id=%s", release.id)
    return release.id


def run_release_publish(release_id: int) -> None:
    _ensure_published_db_is_separate()
    release = get_release(release_id)
    if release is None:
        raise ValueError(f"Release {release_id} does not exist")
    if release.status not in {"built", "published", "superseded"}:
        raise ValueError(
            f"Release {release_id} is not ready to publish (status={release.status})"
        )

    artifact = get_release_artifact(release_id, artifact_type="statements_pack")
    if artifact is None:
        raise ValueError(f"Release {release_id} has no statements artifact")
    resolver_artifact = get_release_artifact(
        release_id, artifact_type="resolver_snapshot"
    )
    if resolver_artifact is None:
        raise ValueError(f"Release {release_id} has no resolver snapshot")

    release_inputs = get_release_inputs(release_id)
    if not release_inputs:
        raise ValueError(f"Release {release_id} has no dataset inputs")

    dataset_names = [str(item["dataset_name"]) for item in release_inputs]
    pack_path = get_artifact_store().resolve_path(str(artifact["storage_key"]))
    resolver_path = get_artifact_store().resolve_path(
        str(resolver_artifact["storage_key"])
    )

    try:
        _load_resolver_snapshot(resolver_path)
        _load_release_into_published_db(dataset_names, pack_path)
        update_release(release_id, status="published", published=True)
    except Exception as exc:
        update_release(release_id, status="failed", error_message=str(exc))
        raise

    log.info("Release published: release_id=%s", release_id)


def _load_release_into_published_db(dataset_names: list[str], pack_path: Path) -> None:
    init_published_database(PUBLISHED_SQL_URI)
    store = get_sql_store(dataset_names, uri=PUBLISHED_SQL_URI)

    with store.engine.begin() as conn:
        conn.execute(delete(store.table))

    with store.writer() as writer:
        with pack_path.open("rb") as fh:
            for stmt in read_pack_statements(fh):
                writer.add_statement(stmt)

    refresh_postgres_search(PUBLISHED_SQL_URI)


def _load_resolver_snapshot(path: Path) -> None:
    target_engine = init_published_database(PUBLISHED_SQL_URI)
    target_resolver = Resolver(target_engine, MetaData(), create=False)

    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"Invalid resolver snapshot: {path}")

    with target_engine.begin() as target_conn:
        target_conn.execute(delete(target_resolver._table))
        if rows:
            target_conn.execute(
                target_resolver._table.insert(), [dict(row) for row in rows]
            )


def _write_resolver_snapshot(path: Path) -> None:
    source_engine = get_engine(SQL_URI)
    source_resolver = Resolver(source_engine, MetaData(), create=False)

    with source_engine.connect() as source_conn:
        rows = (
            source_conn.execute(
                select(source_resolver._table).where(
                    source_resolver._table.c.deleted_at.is_(None)
                )
            )
            .mappings()
            .all()
        )

    path.write_text(json.dumps([dict(row) for row in rows], indent=2, sort_keys=True))


def _write_approved_ner_snapshot(path: Path) -> None:
    engine = init_database()
    table = get_ner_candidates_table()
    with engine.connect() as conn:
        rows = (
            conn.execute(select(table).where(table.c.status == "approved"))
            .mappings()
            .all()
        )
    path.write_text(json.dumps([dict(row) for row in rows], indent=2, sort_keys=True))


def _resolve_dataset_names(dataset_names: Optional[Iterable[str]]) -> list[str]:
    if dataset_names:
        configs = []
        for dataset_name in dataset_names:
            configs.extend(find_datasets(dataset_name))
    else:
        configs = find_datasets()
    if not configs:
        raise ValueError("No datasets found for release build")
    return [load_config(config).name for config in configs]


def _ensure_published_db_is_separate() -> None:
    if PUBLISHED_SQL_URI == SQL_URI:
        raise ValueError(
            "MUCKRAKE_PUBLISHED_DATABASE_URL must point to a separate published database before release-publish can run"
        )
