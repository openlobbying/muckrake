import logging
from pathlib import Path

from muckrake.artifacts import get_artifact_store
from muckrake.dataset import find_datasets, get_dataset_path, load_config
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.runs import get_dataset_run, get_dataset_run_artifact
from muckrake.search import refresh_search_index
from muckrake.store import get_sql_store

log = logging.getLogger(__name__)


def resolve_dataset_pack_path(dataset_name: str, run_id: int | None = None) -> Path:
    if run_id is not None:
        run = get_dataset_run(run_id)
        if run is None:
            raise ValueError(f"Dataset run {run_id} does not exist")
        if run.dataset_name != dataset_name:
            raise ValueError(
                f"Dataset run {run_id} belongs to {run.dataset_name}, not {dataset_name}"
            )
        artifact = get_dataset_run_artifact(run_id, artifact_type="statements_pack")
        if artifact is None:
            raise ValueError(f"Dataset run {run_id} has no statements artifact")
        return get_artifact_store().resolve_path(artifact.storage_key)

    return get_dataset_path(dataset_name) / "statements.pack.csv"


def load_dataset_statements(dataset_name: str, writer, run_id: int | None = None):
    """Replace a dataset's statements with its pack, inside the writer's transaction."""
    pack_path = resolve_dataset_pack_path(dataset_name, run_id=run_id)
    if not pack_path.exists():
        log.warning(f"No statements found for {dataset_name}; keeping what is loaded")
        return

    log.info(f"Loading {dataset_name} into database...")
    writer.replace(writer.store.table.c.dataset == dataset_name)
    for stmt in iter_dataset_statements(dataset_name, pack_path):
        # The SQLWriter will automatically apply canonical_id resolution
        writer.add_statement(stmt)


def run_load(dataset_name: str | None = None, run_id: int | None = None):
    configs = find_datasets(dataset_name)
    if not configs:
        log.error(f"No datasets found matching '{dataset_name}'")
        return

    if run_id is not None and len(configs) != 1:
        raise ValueError("--run-id requires exactly one dataset")

    dataset_names = [load_config(c).name for c in configs]
    store = get_sql_store(dataset_names)

    # One transaction for every dataset: each is cleared and reloaded, and a
    # failure anywhere rolls back to what was loaded before.
    with store.writer() as writer:
        for ds_name in dataset_names:
            load_dataset_statements(ds_name, writer, run_id=run_id)

    refresh_search_index()
