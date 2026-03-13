import logging
import shutil
from typing import Iterable, Set, List, Optional

from followthemoney import DS, SE, Statement
from followthemoney.dataset import Dataset
from nomenklatura.resolver import Resolver, Identifier
from nomenklatura.store.level import LevelDBStore
from nomenklatura.store.sql import SQLStore, SQLView, SQLWriter
from nomenklatura.db import get_engine, get_metadata
from sqlalchemy import select

from muckrake.settings import SQL_URI, LEVEL_PATH
from muckrake.id import is_org_id

# Reduce batch size to avoid SQLite parameter limit (999 or 32766)
# With ~13 columns per statement, 500 statements = ~6500 parameters (safe)
SQLWriter.BATCH_STATEMENTS = 500

# Monkey patch Nomenklatura's Identifier to prioritize org-id.guide IDs
# This ensures GB-COH- style IDs win over NK- or Q- IDs during merges.
original_init = Identifier.__init__


def patched_init(self, id: str):
    original_init(self, id)
    if is_org_id(id):
        # Weight 1: Hashed/Dataset IDs
        # Weight 2: NK- (Nomenklatura random)
        # Weight 3: Q (Wikidata)
        # Weight 4: Org-IDs (Companies House, etc)
        self.weight = 4
        self.canonical = True


Identifier.__init__ = patched_init

log = logging.getLogger(__name__)


class CombinedDataset(Dataset):
    """A virtual dataset that combines multiple leaf datasets."""

    def __init__(self, name: str, datasets: Iterable[str]):
        super().__init__({"name": name, "title": name})
        self._leaf_names = set(datasets)

    @property
    def dataset_names(self) -> List[str]:
        return [self.name] + list(self._leaf_names)

    @property
    def leaf_names(self) -> Set[str]:
        return self._leaf_names


def get_resolver(begin: bool = False) -> Resolver:
    """Get the resolver backed by the main database."""
    engine = get_engine(SQL_URI)
    resolver = Resolver(engine, get_metadata(), create=True)
    if begin:
        resolver.begin()
    return resolver


def get_level_store(dataset_names: Iterable[str], fresh: bool = False) -> LevelDBStore:
    """Get a LevelDB store for processing."""
    if fresh and LEVEL_PATH.exists():
        shutil.rmtree(LEVEL_PATH)

    LEVEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = CombinedDataset("all", dataset_names)
    return LevelDBStore(dataset, get_resolver(begin=True), LEVEL_PATH)


class MergedSQLView(SQLView[DS, SE]):
    """Custom SQL view that properly merges entities with the same canonical_id.

    When querying for an entity by its canonical ID, this view collects ALL statements
    from all entities that were merged into that canonical ID and assembles them into
    a single entity with the most specific schema.
    """

    def get_entity(self, id: str) -> Optional[SE]:
        """Get entity by canonical ID, merging all statements from merged entities."""
        table = self.store.table
        q = select(table)
        q = q.where(table.c.canonical_id == id)
        q = q.where(table.c.dataset.in_(self.dataset_names))
        # Order by entity_id to ensure consistent grouping if needed for debugging,
        # but we'll collect ALL statements regardless
        q = q.order_by(table.c.entity_id)

        # Collect ALL statements with this canonical_id
        all_statements: List[Statement] = []
        for stmt in self.store._iterate_stmts(q, stream=False):
            all_statements.append(stmt)

        if not all_statements:
            return None

        # Assemble into a single entity - from_statements will compute the
        # most specific common schema (e.g., Person over LegalEntity)
        return self.store.assemble(all_statements)


class MergedSQLStore(SQLStore[DS, SE]):
    """Custom SQL store that uses MergedSQLView."""

    def view(self, scope: DS, external: bool = False) -> SQLView[DS, SE]:
        return MergedSQLView(self, scope, external=external)


def get_sql_store(dataset_names: Iterable[str], uri: str = SQL_URI) -> MergedSQLStore:
    """Get a SQL store for serving with proper entity merging."""
    dataset = CombinedDataset("all", dataset_names)
    return MergedSQLStore(dataset, get_resolver(begin=True), uri=uri)
