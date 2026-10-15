from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import psycopg
from followthemoney.statement.serialize import PackStatementWriter, read_pack_statements
from nomenklatura.db import get_engine, make_statement_table
from nomenklatura.resolver import Linker, Resolver
from sqlalchemy import MetaData, delete, desc, select, text, update
from sqlalchemy.engine import Connection, Engine

from muckrake.artifacts import get_artifact_store
from muckrake.dataset import find_datasets, load_config
from muckrake.db import (
    create_search_view,
    get_release_artifacts_table,
    get_release_inputs_table,
    get_releases_table,
    init_database,
    init_published_database,
    is_postgres_uri,
)
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.runs import (
    detect_code_version,
    get_dataset_run_artifact,
    get_latest_successful_run,
    utc_now_iso,
)
from muckrake.search import refresh_search_index
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
        assert result.inserted_primary_key is not None
        release_id = result.inserted_primary_key[0]
        row = conn.execute(select(table).where(table.c.id == release_id)).mappings().one()
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
        row = conn.execute(select(table).where(table.c.id == release_id)).mappings().first()
    if row is None:
        return None
    return Release(**row)


def list_releases(limit: int = 20) -> list[Release]:
    engine = init_database()
    table = get_releases_table()
    with engine.begin() as conn:
        rows = conn.execute(select(table).order_by(desc(table.c.id)).limit(limit)).mappings().all()
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
                metadata_json=json.dumps(metadata, sort_keys=True) if metadata else None,
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
    dataset_names: Iterable[str] | None = None,
    notes: str | None = None,
) -> int:
    selected = _resolve_dataset_names(dataset_names)
    dataset_runs: list[tuple[str, int, Path]] = []
    # Runs that finished `partial`: what each is known to be missing.
    incomplete: dict[str, dict[str, Any]] = {}
    for dataset_name in selected:
        run = get_latest_successful_run(dataset_name)
        if run is None:
            raise ValueError(f"No successful dataset run found for {dataset_name}")
        artifact = get_dataset_run_artifact(run.id, artifact_type="statements_pack")
        if artifact is None:
            raise ValueError(f"Dataset run {run.id} has no statements artifact")
        path = get_artifact_store().resolve_path(artifact.storage_key)
        dataset_runs.append((dataset_name, run.id, path))
        if run.status == "partial":
            units = json.loads(run.stats_json or "{}").get("units", {})
            incomplete[dataset_name] = {
                "failed_units": units.get("failed", 0),
                "failures_by_error": units.get("failures_by_error", {}),
                "warnings_by_reason": units.get("warnings_by_reason", {}),
            }
            log.warning(
                "Release input %s (run %s) is partial: %d failed units, %d completeness warnings",
                dataset_name,
                run.id,
                units.get("failed", 0),
                units.get("warnings", 0),
            )

    release = create_release(notes=notes)
    store = get_artifact_store()
    temp_dir = Path(tempfile.mkdtemp(prefix=f"muckrake-release-{release.id}-"))
    temp_pack = temp_dir / "statements.pack.csv"
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

        manifest = {
            "release_id": release.id,
            "status": "built",
            "dataset_runs": [
                {
                    "dataset_name": name,
                    "dataset_run_id": run_id,
                    **({"incomplete": incomplete[name]} if name in incomplete else {}),
                }
                for name, run_id, _ in dataset_runs
            ],
            "artifacts": [
                {
                    "artifact_type": "statements_pack",
                    "storage_key": stored_pack.storage_key,
                    "sha256": stored_pack.sha256,
                    "size_bytes": stored_pack.size_bytes,
                }
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
        raise ValueError(f"Release {release_id} is not ready to publish (status={release.status})")

    artifact = get_release_artifact(release_id, artifact_type="statements_pack")
    if artifact is None:
        raise ValueError(f"Release {release_id} has no statements artifact")

    release_inputs = get_release_inputs(release_id)
    if not release_inputs:
        raise ValueError(f"Release {release_id} has no dataset inputs")

    dataset_names = [str(item["dataset_name"]) for item in release_inputs]
    pack_path = get_artifact_store().resolve_path(str(artifact["storage_key"]))

    try:
        _copy_resolver_state()
        _load_release_into_published_db(dataset_names, pack_path)
        update_release(release_id, status="published", published=True)
    except Exception as exc:
        update_release(release_id, status="failed", error_message=str(exc))
        raise

    log.info("Release published: release_id=%s", release_id)


def _load_release_into_published_db(dataset_names: list[str], pack_path: Path) -> None:
    engine = init_published_database(PUBLISHED_SQL_URI)
    store = get_sql_store(dataset_names, uri=PUBLISHED_SQL_URI)

    if is_postgres_uri(PUBLISHED_SQL_URI):
        _swap_in_release_postgres(engine, store.linker, pack_path)
        return

    # Clear and rewrite in one transaction, so readers keep seeing the previous
    # release until this one commits, and a failure leaves it in place.
    with store.writer() as writer:
        writer.replace()
        with pack_path.open("rb") as fh:
            for stmt in read_pack_statements(fh):
                writer.add_statement(stmt)

    refresh_search_index(PUBLISHED_SQL_URI)


def _swap_in_release_postgres(engine: Engine, linker: Linker[Any], pack_path: Path) -> None:
    """Build the release in new tables and swap them in, in one transaction.

    The pack is streamed with COPY into a temporary table, deduplicated into
    ``statement_new`` and indexed there, along with a new search view. Swapping
    is a few renames at the end, so readers see the previous release until the
    commit and are only blocked for the swap itself. Statements repeated in the
    pack resolve as the row-by-row upsert does: the last copy wins, except for
    ``first_seen``, which comes from the first.
    """
    columns = [column.name for column in make_statement_table(MetaData()).columns]
    column_sql = ", ".join(f'"{name}"' for name in columns)
    select_sql = ", ".join(
        "FIRST_VALUE(first_seen) OVER (PARTITION BY id ORDER BY seq)"
        if name == "first_seen"
        else f'"{name}"'
        for name in columns
    )
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout = 0"))
        conn.execute(
            text("CREATE TEMP TABLE statement_load (seq bigint, LIKE statement) ON COMMIT DROP")
        )
        driver = cast(psycopg.Connection[Any], conn.connection.driver_connection)
        with (
            driver.cursor() as cursor,
            cursor.copy(f"COPY statement_load (seq, {column_sql}) FROM STDIN") as copy,
            pack_path.open("rb") as fh,
        ):
            for seq, stmt in enumerate(read_pack_statements(fh)):
                if stmt.entity_id is None:
                    continue
                stmt.canonical_id = linker.get_canonical(stmt.entity_id)
                row = stmt.to_db_row()
                copy.write_row([seq, *(row[name] for name in columns)])

        make_statement_table(MetaData(), name="statement_new").create(conn)
        conn.execute(
            text(
                f"INSERT INTO statement_new ({column_sql}) "
                f"SELECT DISTINCT ON (id) {select_sql} FROM statement_load "
                "ORDER BY id, seq DESC"
            )
        )
        create_search_view(conn, view="entity_search_new", table="statement_new")

        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS entity_search"))
        conn.execute(text("DROP TABLE statement"))
        conn.execute(text("ALTER TABLE statement_new RENAME TO statement"))
        conn.execute(text("ALTER MATERIALIZED VIEW entity_search_new RENAME TO entity_search"))
        _rename_indexes(conn, "statement", "statement_new", "statement")
        _rename_indexes(conn, "entity_search", "entity_search_new", "entity_search")


def _rename_indexes(conn: Connection, relation: str, old: str, new: str) -> None:
    names = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :relation"),
        {"relation": relation},
    ).scalars()
    for name in list(names):
        if old in name:
            conn.execute(text(f'ALTER INDEX "{name}" RENAME TO "{name.replace(old, new)}"'))


def _copy_resolver_state() -> None:
    source_engine = get_engine(SQL_URI)
    target_engine = init_published_database(PUBLISHED_SQL_URI)
    source_resolver: Resolver = Resolver(source_engine, MetaData(), create=False)
    target_resolver: Resolver = Resolver(target_engine, MetaData(), create=False)

    with source_engine.connect() as source_conn:
        rows = (
            source_conn.execute(
                select(source_resolver._table).where(source_resolver._table.c.deleted_at.is_(None))
            )
            .mappings()
            .all()
        )

    with target_engine.begin() as target_conn:
        target_conn.execute(delete(target_resolver._table))
        if rows:
            target_conn.execute(target_resolver._table.insert(), [dict(row) for row in rows])


def _resolve_dataset_names(dataset_names: Iterable[str] | None) -> list[str]:
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
            "MUCKRAKE_PUBLISHED_DATABASE_URL must point to a separate published "
            "database before release-publish can run"
        )
