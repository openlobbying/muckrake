import logging

from followthemoney import model
from nomenklatura.db import make_session
from nomenklatura.judgement import Judgement
from nomenklatura.matching import DefaultAlgorithm, get_algorithm
from nomenklatura.resolver import Resolver
from nomenklatura.xref import xref as nk_xref

from muckrake.dataset import find_datasets, get_dataset_path, load_config
from muckrake.db import open_resolver
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.settings import DATA_PATH, PROFILE_URL, SQL_URI
from muckrake.store import get_level_store

log = logging.getLogger(__name__)


def load_statements(store, dataset_names) -> set[str]:
    """Load statements from pack files into a store; returns the entity IDs loaded."""
    log.info("Loading statements into store...")
    entity_ids: set[str] = set()
    with store.writer() as writer:
        for ds_name in dataset_names:
            pack_path = get_dataset_path(ds_name) / "statements.pack.csv"
            if pack_path.exists():
                for stmt in iter_dataset_statements(ds_name, pack_path):
                    writer.add_statement(stmt)
                    entity_ids.add(stmt.entity_id)
    return entity_ids


def prune_stale_suggestions(resolver: Resolver, entity_ids: set[str]) -> int:
    """Soft-delete suggestions whose source or target is no longer in the store.

    An ID is present if it's one of ``entity_ids`` or the canonical ID of a
    cluster that contains one. Judged edges are never touched. Returns how many
    suggestions were removed.
    """
    present = entity_ids | {resolver.get_canonical(entity_id) for entity_id in entity_ids}
    stale = [
        edge
        for edge in resolver.all_edges(include_suggestions=True)
        if edge.judgement == Judgement.NO_JUDGEMENT
        and (edge.source.id not in present or edge.target.id not in present)
    ]
    for edge in stale:
        # nomenklatura has no public way to soft-delete one edge.
        resolver._remove_edge(edge)
    return len(stale)


def run_xref(
    limit: int = 50000,
    threshold: float | None = None,
    algorithm: str = DefaultAlgorithm.NAME,
    schema: str | None = None,
    focus_dataset: str | None = None,
) -> None:
    """Generate deduplication candidates."""
    all_configs = find_datasets()
    dataset_names = [load_config(c).name for c in all_configs]

    store = get_level_store(dataset_names, fresh=True)
    index_dir = DATA_PATH / "xref-index"

    algorithm_type = get_algorithm(algorithm)
    if algorithm_type is None:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    entity_ids = load_statements(store, dataset_names)

    # xref commits its suggestions in batches as it goes (session checkpoints).
    with make_session(SQL_URI) as session:
        resolver: Resolver = Resolver(session, create=True)
        resolver.load_into_memory()
        # Suggestions for entities that are gone (replaced by NER splits, or no
        # longer crawled) would otherwise stay in the review queue, and an
        # auto-merge threshold would turn them into judgements about nothing.
        removed = prune_stale_suggestions(resolver, entity_ids)
        log.info("Removed %s suggestions for entities no longer in the store.", removed)
        nk_xref(
            resolver,
            session,
            store,
            index_dir,
            limit=limit,
            range=model.get(schema) if schema else None,
            auto_threshold=threshold,
            algorithm=algorithm_type,
            focus_datasets={focus_dataset} if focus_dataset else None,
            user="muckrake/xref",
        )
    log.info("Xref complete.")


def run_dedupe() -> None:
    """Interactively judge candidates."""
    from nomenklatura.tui import dedupe_ui

    all_configs = find_datasets()
    dataset_names = [load_config(c).name for c in all_configs]

    store = get_level_store(dataset_names, fresh=False)
    if not any(store.view(store.dataset).entities()):
        load_statements(store, dataset_names)

    with make_session(SQL_URI) as session:
        resolver: Resolver = Resolver(session, create=True)
        resolver.load_into_memory()
        dedupe_ui(resolver, session, store, url_base=PROFILE_URL)


def run_merge(entity_ids: list[str], force: bool = False) -> None:
    """Merge multiple entities into a canonical identity."""
    if len(entity_ids) < 2:
        raise ValueError("Need multiple IDs to merge!")

    with open_resolver() as resolver:
        canonical_id = resolver.get_canonical(entity_ids[0])
        for other_id in entity_ids[1:]:
            if resolver.get_canonical(other_id) == canonical_id:
                continue

            resolver.decide(canonical_id, other_id, Judgement.POSITIVE, user="muckrake/manual")


def run_dedupe_explode(entity_id: str) -> None:
    """Undo deduplication by exploding a resolved entity cluster."""
    with open_resolver() as resolver:
        canonical_id = resolver.get_canonical(entity_id)
        restored = 0
        for part_id in resolver.explode(canonical_id):
            restored += 1
            log.info("Restored separate entity: %s", part_id)
    log.info("Exploded cluster %s (%s entities)", canonical_id, restored)


def run_prune() -> None:
    """Remove dedupe candidates from resolver file."""
    with open_resolver() as resolver:
        resolver.prune()
    log.info("Resolver pruned.")
