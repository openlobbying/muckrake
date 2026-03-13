import logging
from typing import Optional

from followthemoney import model
from nomenklatura.judgement import Judgement
from nomenklatura.matching import DefaultAlgorithm, get_algorithm
from nomenklatura.xref import xref as nk_xref

from muckrake.dataset import find_datasets, get_dataset_path, load_config
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.settings import DATA_PATH
from muckrake.store import get_level_store, get_resolver

log = logging.getLogger(__name__)


def load_statements(store, dataset_names):
    """Load statements from pack files into a store."""
    log.info("Loading statements into store...")
    with store.writer() as writer:
        for ds_name in dataset_names:
            pack_path = get_dataset_path(ds_name) / "statements.pack.csv"
            if pack_path.exists():
                for stmt in iter_dataset_statements(ds_name, pack_path):
                    writer.add_statement(stmt)


def run_xref(
    limit: int = 5000,
    threshold: Optional[float] = None,
    algorithm: str = DefaultAlgorithm.NAME,
    schema: Optional[str] = None,
    focus_dataset: Optional[str] = None,
) -> None:
    """Generate deduplication candidates."""
    all_configs = find_datasets()
    dataset_names = [load_config(c).name for c in all_configs]

    store = get_level_store(dataset_names, fresh=True)
    resolver = get_resolver()
    index_dir = DATA_PATH / "xref-index"

    algorithm_type = get_algorithm(algorithm)
    if algorithm_type is None:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    load_statements(store, dataset_names)

    resolver.begin()
    nk_xref(
        resolver,
        store,
        index_dir,
        limit=limit,
        range=model.get(schema) if schema else None,
        auto_threshold=threshold,
        algorithm=algorithm_type,
        focus_dataset=focus_dataset,
        user="muckrake/xref",
    )
    resolver.commit()
    log.info("Xref complete.")


def run_dedupe() -> None:
    """Interactively judge candidates."""
    from nomenklatura.tui import dedupe_ui

    all_configs = find_datasets()
    dataset_names = [load_config(c).name for c in all_configs]

    store = get_level_store(dataset_names, fresh=False)
    if not any(store.view(store.dataset).entities()):
        load_statements(store, dataset_names)

    resolver = get_resolver()
    resolver.begin()
    dedupe_ui(resolver, store, url_base="https://openlobbying.org/profile/%s/")
    resolver.commit()


def run_merge(entity_ids: list[str], force: bool = False) -> None:
    """Merge multiple entities into a canonical identity."""
    if len(entity_ids) < 2:
        raise ValueError("Need multiple IDs to merge!")

    resolver = get_resolver()
    resolver.begin()
    try:
        canonical_id = resolver.get_canonical(entity_ids[0])
        for other_id in entity_ids[1:]:
            if resolver.get_canonical(other_id) == canonical_id:
                continue

            resolver.decide(
                canonical_id, other_id, Judgement.POSITIVE, user="muckrake/manual"
            )

        resolver.commit()
    except Exception:
        resolver.rollback()
        raise


def run_dedupe_explode(entity_id: str) -> None:
    """Undo deduplication by exploding a resolved entity cluster."""
    resolver = get_resolver()
    resolver.begin()
    try:
        canonical_id = resolver.get_canonical(entity_id)
        restored = 0
        for part_id in resolver.explode(canonical_id):
            restored += 1
            log.info("Restored separate entity: %s", part_id)
        resolver.commit()
        log.info("Exploded cluster %s (%s entities)", canonical_id, restored)
    except Exception:
        resolver.rollback()
        raise


def run_prune() -> None:
    """Remove dedupe candidates from resolver file."""
    resolver = get_resolver()
    resolver.begin()
    try:
        resolver.prune()
        resolver.commit()
        log.info("Resolver pruned.")
    except Exception:
        resolver.rollback()
        raise
