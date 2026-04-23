import importlib.util
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional
from followthemoney.statement.serialize import PackStatementWriter

from muckrake.dataset import Dataset, load_config, get_dataset_path
from muckrake.artifacts import get_artifact_store
from muckrake.runs import (
    config_version,
    create_dataset_run,
    detect_code_version,
    finish_dataset_run,
    get_latest_successful_artifact,
    make_storage_prefix,
    record_dataset_run_artifact,
)

log = logging.getLogger(__name__)


def load_timestamps(path: Path) -> Dict[str, str]:
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

    # Determine the package hierarchy based on directory structure relative to datasets/
    datasets_root = Path("datasets").resolve()
    try:
        # Try to find the path relative to the datasets root
        rel_path = crawler_path.parent.relative_to(datasets_root)
        parts = ["muckrake", "crawler"] + list(rel_path.parts)
    except ValueError:
        # Fallback if crawler is not in datasets/ or we can't find the root
        parts = ["muckrake", "crawler", ds.name]

    import types
    import sys
    
    # Initialize all parent packages to ensure relative imports work.
    # We walk down the hierarchy and create virtual modules for each level.
    for i in range(1, len(parts) + 1):
        pkg_name = ".".join(parts[:i])
        if pkg_name not in sys.modules:
            mod = types.ModuleType(pkg_name)
            if i >= 2: # muckrake.crawler and below
                # Map this virtual package to the corresponding filesystem directory
                rel_parts = parts[2:i]
                fs_path = datasets_root.joinpath(*rel_parts)
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


def run_crawl(config_path: Path, output: Optional[str] = None):
    """Helper to run a single crawl."""
    ds_config = load_config(config_path)
    dataset_name = ds_config.name

    if output:
        output_path = Path(output)
    else:
        output_path = get_dataset_path(dataset_name) / "statements.pack.csv"

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
    store = get_artifact_store()
    storage_prefix = make_storage_prefix(dataset_name, dataset_run.id)

    if output_path.as_posix() == "-":
        writer = PackStatementWriter(sys.stdout)
        temp_output_path = None
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"muckrake-crawl-{dataset_name}-"))
        temp_output_path = temp_dir / "statements.pack.csv"
        writer = PackStatementWriter(open(temp_output_path, "w"))

    ds: Dataset | None = None
    try:
        ds = Dataset(config_path, writer, timestamps=timestamps)
        execute_crawler(config_path, ds)
    except Exception as exc:
        finish_dataset_run(dataset_run.id, "failed", error_message=str(exc))
        raise
    finally:
        if ds is not None:
            ds.close()
        writer.close()

    if output_path.as_posix() == "-":
        finish_dataset_run(dataset_run.id, "succeeded")
        return

    try:
        stored_pack = store.put_file(
            temp_output_path,
            f"{storage_prefix}/statements.pack.csv",
        )
        record_dataset_run_artifact(
            dataset_run.id,
            artifact_type="statements_pack",
            storage_backend=stored_pack.storage_backend,
            storage_key=stored_pack.storage_key,
            content_type="text/csv",
            sha256=stored_pack.sha256,
            size_bytes=stored_pack.size_bytes,
            metadata={"dataset_name": dataset_name},
        )
        manifest = {
            "dataset_name": dataset_name,
            "run_id": dataset_run.id,
            "run_type": "crawl",
            "status": "succeeded",
            "code_version": dataset_run.code_version,
            "config_version": dataset_run.config_version,
            "artifacts": [
                {
                    "artifact_type": "statements_pack",
                    "storage_backend": stored_pack.storage_backend,
                    "storage_key": stored_pack.storage_key,
                    "sha256": stored_pack.sha256,
                    "size_bytes": stored_pack.size_bytes,
                }
            ],
        }
        stored_manifest = store.put_json(manifest, f"{storage_prefix}/manifest.json")
        record_dataset_run_artifact(
            dataset_run.id,
            artifact_type="manifest",
            storage_backend=stored_manifest.storage_backend,
            storage_key=stored_manifest.storage_key,
            content_type="application/json",
            sha256=stored_manifest.sha256,
            size_bytes=stored_manifest.size_bytes,
            metadata={"dataset_name": dataset_name},
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp_output_path, output_path)
        finish_dataset_run(
            dataset_run.id,
            "succeeded",
            stats={
                "output_path": output_path.as_posix(),
                "statements_artifact_key": stored_pack.storage_key,
                "manifest_artifact_key": stored_manifest.storage_key,
                "previous_artifact_key": (
                    previous_artifact.storage_key if previous_artifact is not None else None
                ),
            },
        )
    except Exception as exc:
        finish_dataset_run(dataset_run.id, "failed", error_message=str(exc))
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    log.info(
        "Crawl complete: %s -> %s (run_id=%s)",
        dataset_name,
        output_path,
        dataset_run.id,
    )
