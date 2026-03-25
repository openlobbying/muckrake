import logging
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from followthemoney import model
from nomenklatura.judgement import Judgement
from nomenklatura.matching import DefaultAlgorithm, get_algorithm
from nomenklatura.xref import xref as nk_xref

from muckrake.dataset import find_datasets, get_dataset_path, load_config
from muckrake.extract.ner.materialize import iter_dataset_statements
from muckrake.settings import DATA_PATH
from muckrake.store import get_level_store, get_resolver
from muckrake.dedupe.unknown_links import UnknownLinksStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExternalActionContext:
    left: object
    right: object
    score: float
    resolver: object
    store: object
    view: object


@dataclass(frozen=True)
class ExternalAction:
    name: str
    key: str
    label: str
    callback: Callable[[ExternalActionContext], str | None | Awaitable[str | None]]


from nomenklatura.tui.app import DedupeApp


class HookedDedupeApp(DedupeApp):
    """A nomenklatura DedupeApp with extra key bindings.

    This is implemented in muckrake (not nomenklatura) to keep schema-specific
    behavior out of nomenklatura while still allowing side-effect actions.
    """

    # Ensure we keep using nomenklatura's bundled stylesheet even though this
    # subclass lives in muckrake.
    import nomenklatura.tui.app as _nk_tui_app

    CSS_PATH = str(Path(_nk_tui_app.__file__).with_name("app.tcss"))

    def __init__(self, actions: list[ExternalAction]):
        super().__init__()
        self._actions = {a.name: a for a in actions}

        for action in actions:
            # textual action args are parsed via ast.literal_eval
            self.bind(
                action.key, f"external({action.name!r})", description=action.label
            )

    async def _flash(self, message: str, seconds: float = 1.0) -> None:
        import asyncio

        self.dedupe.message = message
        self.force_render()
        await asyncio.sleep(seconds)
        self.dedupe.message = None
        self.force_render()

    async def action_external(self, name: str) -> None:
        action = self._actions.get(name)
        if action is None:
            return
        if getattr(self, "dedupe", None) is None:
            return
        if self.dedupe.left is None or self.dedupe.right is None:
            await self._flash("No candidate loaded.")
            return

        ctx = ExternalActionContext(
            left=self.dedupe.left,
            right=self.dedupe.right,
            score=float(getattr(self.dedupe, "score", 0.0) or 0.0),
            resolver=self.dedupe.resolver,
            store=self.dedupe.store,
            view=self.dedupe.view,
        )

        try:
            result = action.callback(ctx)
            if inspect.isawaitable(result):
                result = await result
            await self._flash(result or "Done.")
        except Exception as exc:
            log.exception("External action failed: %s", action.name)
            await self._flash(f"Action failed: {exc}")


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
    from nomenklatura.tui.app import DedupeState

    all_configs = find_datasets()
    dataset_names = [load_config(c).name for c in all_configs]

    store = get_level_store(dataset_names, fresh=False)
    if not any(store.view(store.dataset).entities()):
        load_statements(store, dataset_names)

    resolver = get_resolver()
    resolver.begin()

    links = UnknownLinksStore()

    def add_unknown_link(ctx: ExternalActionContext) -> str:
        left_id = getattr(ctx.left, "id", None)
        right_id = getattr(ctx.right, "id", None)
        if left_id is None or right_id is None:
            return "Missing entity IDs."

        inserted = links.add(
            str(left_id),
            str(right_id),
            score=ctx.score,
            user="muckrake/unknown-link",
        )
        return "Saved UnknownLink." if inserted else "UnknownLink already exists."

    app = HookedDedupeApp(
        actions=[
            ExternalAction(
                name="unknown_link",
                key="o",
                label="Link (UnknownLink)",
                callback=add_unknown_link,
            )
        ]
    )
    app.dedupe = DedupeState(
        resolver,
        store,
        url_base="https://openlobbying.org/profile/%s/",
    )
    app.run()
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
