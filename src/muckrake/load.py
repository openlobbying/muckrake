import logging
from typing import Optional

from muckrake.dataset import find_datasets, load_config, get_dataset_path
from muckrake.db import refresh_postgres_search
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.store import get_sql_store

log = logging.getLogger(__name__)


def load_dataset_statements(dataset_name: str, writer):
    pack_path = get_dataset_path(dataset_name) / "statements.pack.csv"
    if not pack_path.exists():
        log.warning(f"No statements found for {dataset_name}")
        return

    log.info(f"Loading {dataset_name} into database...")
    for stmt in iter_dataset_statements(dataset_name, pack_path):
        # The SQLWriter will automatically apply canonical_id resolution
        writer.add_statement(stmt)


def run_load(dataset_name: Optional[str] = None):
    configs = find_datasets(dataset_name)
    if not configs:
        log.error(f"No datasets found matching '{dataset_name}'")
        return

    dataset_names = [load_config(c).name for c in configs]
    store = get_sql_store(dataset_names)

    # Clear existing statements for these datasets in a separate transaction
    from sqlalchemy import delete

    with store.engine.begin() as conn:
        for ds_name in dataset_names:
            log.info(f"Clearing {ds_name} from database...")
            delete_q = delete(store.table).where(store.table.c.dataset == ds_name)
            conn.execute(delete_q)

    # Load new statements
    with store.writer() as writer:
        for ds_name in dataset_names:
            load_dataset_statements(ds_name, writer)

    refresh_postgres_search()
