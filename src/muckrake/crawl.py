import importlib.util
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from followthemoney.statement.serialize import PackStatementWriter

from muckrake.artifacts import LocalArtifactStore, get_artifact_store
from muckrake.dataset import Dataset, get_dataset_path, load_config, resolve_dataset_root
from muckrake.runs import (
    config_version,
    create_dataset_run,
    detect_code_version,
    finish_dataset_run,
    get_latest_crawl_run,
    get_latest_successful_artifact,
    make_storage_prefix,
    record_dataset_run_artifact,
)
from muckrake.units import UnitLedger, UnitRecord, read_ledger

log = logging.getLogger(__name__)


def load_timestamps(path: Path) -> dict[str, str]:
    """Load previous first_seen timestamps from a pack file."""
    timestamps = {}
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        log.info(f"Loading previous state from {path}...")
        try:
            with open(path, "rb") as fh:
                from followthemoney.statement.serialize import read_pack_statements

                for stmt in read_pack_statements(fh):
                    if stmt.id is not None and stmt.first_seen is not None:
                        timestamps[stmt.id] = stmt.first_seen
        except Exception as e:
            log.warning(f"Failed to load previous state: {e}")
    return timestamps


def execute_crawler(config_path: Path, ds: Dataset):
    """Dynamically load and run the crawler script for a dataset."""
    crawler_path = config_path.parent.resolve() / "crawler.py"
    if not crawler_path.exists():
        raise RuntimeError(f"crawler.py not found at {crawler_path}")

    # Build a virtual package hierarchy so relative imports inside dataset code keep working
    datasets_root = resolve_dataset_root(config_path)
    parts = ["muckrake", "crawler"]
    try:
        if datasets_root is None:
            raise ValueError("Dataset root could not be resolved")
        rel_path = crawler_path.parent.relative_to(datasets_root)
        if rel_path.parts:
            parts.extend(rel_path.parts)
        else:
            parts.append(ds.name)
    except ValueError:
        parts.append(ds.name)

    import types

    # Initialize all parent packages to ensure relative imports work.
    # We walk down the hierarchy and create virtual modules for each level.
    for i in range(1, len(parts) + 1):
        pkg_name = ".".join(parts[:i])
        if pkg_name not in sys.modules:
            mod = types.ModuleType(pkg_name)
            if i >= 2:  # muckrake.crawler and below
                # Map this virtual package to the corresponding filesystem directory
                rel_parts = parts[2:i]
                if datasets_root is not None:
                    fs_path = datasets_root.joinpath(*rel_parts)
                else:
                    fs_path = crawler_path.parent
                if fs_path.exists():
                    mod.__path__ = [str(fs_path)]

            # For packages, __package__ should be the name of the package itself.
            mod.__package__ = pkg_name
            sys.modules[pkg_name] = mod

    # The actual crawler module is a submodule of the final package
    pkg_name = ".".join(parts)
    module_name = f"{pkg_name}.crawler"
    spec = importlib.util.spec_from_file_location(module_name, str(crawler_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load crawler from {crawler_path}")

    crawler_module = importlib.util.module_from_spec(spec)
    # Ensure the module knows its package for relative imports
    crawler_module.__package__ = pkg_name
    sys.modules[module_name] = crawler_module
    spec.loader.exec_module(crawler_module)

    if not hasattr(crawler_module, "crawl"):
        raise RuntimeError(f"crawler.py in {ds.name} must define a 'crawl' function")

    crawler_module.crawl(ds)


def find_retry_source(dataset_name: str) -> tuple[Path, list[UnitRecord]]:
    """The pack and unit ledger of a dataset's latest crawl run, for --retry-failed."""
    run = get_latest_crawl_run(dataset_name)
    if run is None:
        raise ValueError(f"No previous crawl of {dataset_name} to retry")
    prefix = make_storage_prefix(dataset_name, run.id)
    store = get_artifact_store()
    pack_path = store.resolve_path(f"{prefix}/statements.pack.csv")
    ledger_path = store.resolve_path(f"{prefix}/units.jsonl")
    if not ledger_path.exists():
        raise ValueError(
            f"Crawl run {run.id} of {dataset_name} has no unit ledger; "
            "--retry-failed needs a crawler that uses dataset.run_unit"
        )
    return pack_path, read_ledger(ledger_path)


def record_run_artifacts(
    store: LocalArtifactStore,
    dataset_run_id: int,
    dataset_name: str,
    storage_prefix: str,
    status: str,
    code_version: str | None,
    config_version: str | None,
) -> str:
    """Record the run's pack, unit ledger and manifest; return the pack's storage key."""
    stored = [
        (store.describe(f"{storage_prefix}/statements.pack.csv"), "statements_pack", "text/csv"),
        (store.describe(f"{storage_prefix}/units.jsonl"), "units", "application/jsonl"),
    ]
    for artifact, artifact_type, content_type in stored:
        record_dataset_run_artifact(
            dataset_run_id,
            artifact_type=artifact_type,
            storage_backend=artifact.storage_backend,
            storage_key=artifact.storage_key,
            content_type=content_type,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            metadata={"dataset_name": dataset_name},
        )
    manifest = {
        "dataset_name": dataset_name,
        "run_id": dataset_run_id,
        "run_type": "crawl",
        "status": status,
        "code_version": code_version,
        "config_version": config_version,
        "artifacts": [
            {
                "artifact_type": artifact_type,
                "storage_backend": artifact.storage_backend,
                "storage_key": artifact.storage_key,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            }
            for artifact, artifact_type, _ in stored
        ],
    }
    stored_manifest = store.put_json(manifest, f"{storage_prefix}/manifest.json")
    record_dataset_run_artifact(
        dataset_run_id,
        artifact_type="manifest",
        storage_backend=stored_manifest.storage_backend,
        storage_key=stored_manifest.storage_key,
        content_type="application/json",
        sha256=stored_manifest.sha256,
        size_bytes=stored_manifest.size_bytes,
        metadata={"dataset_name": dataset_name},
    )
    return stored[0][0].storage_key


def log_unit_summary(dataset_name: str, summary: dict[str, Any]) -> None:
    log.info(
        "%s units: %d succeeded, %d carried over, %d failed",
        dataset_name,
        summary["succeeded"],
        summary["carried"],
        summary["failed"],
    )
    for group, count in summary["failures_by_error"].items():
        log.warning("  %6d x %s", count, group)
    if summary["failed"]:
        log.warning("Re-run the failed units with: muckrake crawl %s --retry-failed", dataset_name)


def run_crawl(config_path: Path, output: str | None = None, retry_failed: bool = False):
    """Crawl one dataset into a new immutable run artifact.

    The pack and unit ledger are written straight into the run's artifact
    directory, so a crawl that crashes or is killed still leaves its completed
    units behind for ``retry_failed`` to carry over.
    """
    ds_config = load_config(config_path)
    dataset_name = ds_config.name
    streaming = output is not None and output == "-"
    if streaming and retry_failed:
        raise ValueError("--retry-failed cannot be combined with streaming output")

    output_path = Path(output) if output else get_dataset_path(dataset_name) / "statements.pack.csv"
    retry_source = find_retry_source(dataset_name) if retry_failed else None

    previous_artifact = get_latest_successful_artifact(dataset_name)
    previous_path = (
        get_artifact_store().resolve_path(previous_artifact.storage_key)
        if previous_artifact is not None
        else output_path
    )
    timestamps = load_timestamps(previous_path)

    dataset_run = create_dataset_run(
        dataset_name=dataset_name,
        run_type="crawl",
        triggered_by="muckrake/crawl",
        code_version=detect_code_version(),
        config_version_value=config_version(config_path),
    )

    if streaming:
        writer = PackStatementWriter(sys.stdout)
        units = UnitLedger(None)
        stream_ds = Dataset(config_path, writer, timestamps=timestamps, units=units)
        try:
            execute_crawler(config_path, stream_ds)
        except Exception as exc:
            finish_dataset_run(dataset_run.id, "failed", error_message=str(exc))
            raise
        finally:
            stream_ds.close()
            writer.flush()
        summary = units.summary()
        log_unit_summary(dataset_name, summary)
        status = "partial" if summary["failed"] else "succeeded"
        finish_dataset_run(dataset_run.id, status, stats={"units": summary})
        return

    store = get_artifact_store()
    storage_prefix = make_storage_prefix(dataset_name, dataset_run.id)
    pack_path = store.resolve_path(f"{storage_prefix}/statements.pack.csv")
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PackStatementWriter(pack_path.open("w", encoding="utf-8"))
    units = UnitLedger(store.resolve_path(f"{storage_prefix}/units.jsonl"), writer)

    def finish(status: str, error_message: str | None = None) -> str:
        summary = units.summary()
        log_unit_summary(dataset_name, summary)
        pack_key = record_run_artifacts(
            store,
            dataset_run.id,
            dataset_name,
            storage_prefix,
            status,
            dataset_run.code_version,
            dataset_run.config_version,
        )
        finish_dataset_run(
            dataset_run.id,
            status,
            error_message=error_message,
            stats={
                "output_path": output_path.as_posix(),
                "statements_artifact_key": pack_key,
                "previous_artifact_key": (
                    previous_artifact.storage_key if previous_artifact is not None else None
                ),
                "units": summary,
            },
        )
        return pack_key

    ds: Dataset | None = None
    try:
        ds = Dataset(config_path, writer, timestamps=timestamps, units=units)
        if retry_source is not None:
            units.carry_over(*retry_source)
        execute_crawler(config_path, ds)
    except BaseException as exc:
        # Includes KeyboardInterrupt: keep whatever completed for --retry-failed.
        if ds is not None:
            ds.close()
        writer.close()
        units.close()
        finish("failed", error_message=f"{type(exc).__name__}: {exc}")
        raise

    ds.close()
    writer.close()
    units.close()
    status = "partial" if units.summary()["failed"] else "succeeded"
    finish(status)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pack_path, output_path)
    log.info(
        "Crawl %s: %s -> %s (run_id=%s)",
        status,
        dataset_name,
        output_path,
        dataset_run.id,
    )
