from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select, update

from muckrake.db import (
    get_dataset_run_artifacts_table,
    get_dataset_runs_table,
    init_database,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def detect_code_version() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def config_version(config_path: Path) -> str:
    return f"sha256:{_sha256_bytes(config_path.read_bytes())}"


def make_storage_prefix(dataset_name: str, run_id: int) -> str:
    return f"dataset-runs/{dataset_name}/{run_id}"


@dataclass
class DatasetRun:
    id: int
    dataset_name: str
    run_type: str
    status: str
    triggered_by: str | None
    code_version: str | None
    config_version: str | None
    run_key: str | None
    error_message: str | None
    stats_json: str | None
    started_at: str
    finished_at: str | None


@dataclass
class DatasetRunArtifact:
    id: int
    dataset_run_id: int
    artifact_type: str
    storage_backend: str
    storage_key: str
    content_type: str | None
    sha256: str
    size_bytes: int
    metadata_json: str | None
    created_at: str


def create_dataset_run(
    dataset_name: str,
    run_type: str = "crawl",
    triggered_by: str | None = "muckrake/crawl",
    code_version: str | None = None,
    config_version_value: str | None = None,
    run_key: str | None = None,
) -> DatasetRun:
    engine = init_database()
    table = get_dataset_runs_table()
    now = utc_now_iso()
    with engine.begin() as conn:
        result = conn.execute(
            table.insert().values(
                dataset_name=dataset_name,
                run_type=run_type,
                status="running",
                triggered_by=triggered_by,
                code_version=code_version,
                config_version=config_version_value,
                run_key=run_key,
                error_message=None,
                stats_json=None,
                started_at=now,
                finished_at=None,
            )
        )
        run_id = result.inserted_primary_key[0]
        row = conn.execute(select(table).where(table.c.id == run_id)).mappings().one()
    return DatasetRun(**row)


def finish_dataset_run(
    run_id: int,
    status: str,
    *,
    error_message: str | None = None,
    stats: dict[str, Any] | None = None,
) -> None:
    engine = init_database()
    table = get_dataset_runs_table()
    with engine.begin() as conn:
        conn.execute(
            update(table)
            .where(table.c.id == run_id)
            .values(
                status=status,
                error_message=error_message,
                stats_json=json.dumps(stats, sort_keys=True) if stats else None,
                finished_at=utc_now_iso(),
            )
        )


def record_dataset_run_artifact(
    run_id: int,
    *,
    artifact_type: str,
    storage_backend: str,
    storage_key: str,
    content_type: str | None,
    sha256: str,
    size_bytes: int,
    metadata: dict[str, Any] | None = None,
) -> DatasetRunArtifact:
    engine = init_database()
    table = get_dataset_run_artifacts_table()
    now = utc_now_iso()
    with engine.begin() as conn:
        result = conn.execute(
            table.insert().values(
                dataset_run_id=run_id,
                artifact_type=artifact_type,
                storage_backend=storage_backend,
                storage_key=storage_key,
                content_type=content_type,
                sha256=sha256,
                size_bytes=size_bytes,
                metadata_json=json.dumps(metadata, sort_keys=True) if metadata else None,
                created_at=now,
            )
        )
        artifact_id = result.inserted_primary_key[0]
        row = conn.execute(select(table).where(table.c.id == artifact_id)).mappings().one()
    return DatasetRunArtifact(**row)


def get_dataset_run(run_id: int) -> DatasetRun | None:
    engine = init_database()
    table = get_dataset_runs_table()
    with engine.begin() as conn:
        row = conn.execute(select(table).where(table.c.id == run_id)).mappings().first()
    if row is None:
        return None
    return DatasetRun(**row)


def get_dataset_run_artifact(
    run_id: int,
    artifact_type: str = "statements_pack",
) -> DatasetRunArtifact | None:
    engine = init_database()
    table = get_dataset_run_artifacts_table()
    with engine.begin() as conn:
        row = conn.execute(
            select(table)
            .where(table.c.dataset_run_id == run_id)
            .where(table.c.artifact_type == artifact_type)
            .order_by(desc(table.c.id))
        ).mappings().first()
    if row is None:
        return None
    return DatasetRunArtifact(**row)


def get_latest_successful_artifact(
    dataset_name: str,
    artifact_type: str = "statements_pack",
) -> DatasetRunArtifact | None:
    engine = init_database()
    runs = get_dataset_runs_table()
    artifacts = get_dataset_run_artifacts_table()
    with engine.begin() as conn:
        row = conn.execute(
            select(artifacts)
            .join(runs, artifacts.c.dataset_run_id == runs.c.id)
            .where(runs.c.dataset_name == dataset_name)
            .where(runs.c.status == "succeeded")
            .where(artifacts.c.artifact_type == artifact_type)
            .order_by(desc(runs.c.started_at), desc(artifacts.c.id))
        ).mappings().first()
    if row is None:
        return None
    return DatasetRunArtifact(**row)


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
