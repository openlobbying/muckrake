import logging
from pathlib import Path
from typing import Optional

from followthemoney.cli.util import write_entity
from muckrake.dataset import find_datasets, load_config
from muckrake.store import get_level_store
from muckrake.dedupe import load_statements

log = logging.getLogger(__name__)


def run_export_ftm(output_path: Path, dataset_name: Optional[str] = None) -> None:
    """Export entities to FollowTheMoney JSON format."""
    all_configs = find_datasets(dataset_name)
    if not all_configs:
        raise ValueError(f"No datasets found matching: {dataset_name}")
        
    dataset_names = [load_config(c).name for c in all_configs]
    
    # Initialize store and load data (fresh=True ensures we have latest from packs)
    store = get_level_store(dataset_names, fresh=True)
    load_statements(store, dataset_names)
    
    view = store.view(store.dataset)
    
    log.info(f"Exporting to {output_path}...")
    count = 0
    with open(output_path, "wb") as fh:
        for entity in view.entities():
            if view.store.linker:
                canonical_id = view.store.linker.get_canonical(entity.id)
                if canonical_id != entity.id:
                    continue
            write_entity(fh, entity)
            count += 1
            if count % 10000 == 0:
                log.info(f"Exported {count} entities...")
    
    log.info(f"Export complete. Total versions: {count}")
