from __future__ import annotations

import logging
import shutil
from collections.abc import Iterable
from types import TracebackType
from typing import TYPE_CHECKING, Any

from followthemoney import DS, SE, Statement
from followthemoney.dataset import Dataset
from nomenklatura import settings as nk_settings
from nomenklatura.store import Store
from nomenklatura.store.sql import SQLStore, SQLView, SQLWriter, make_statement_table
from sqlalchemy import MetaData, delete, select
from sqlalchemy.engine import create_engine

from muckrake.db import get_database_dialect, get_resolver
from muckrake.settings import LEVEL_PATH, SQL_URI

if TYPE_CHECKING:
    from nomenklatura.store.level import LevelDBStore

log = logging.getLogger(__name__)
SQL_BATCH_STATEMENTS = 500


class CombinedDataset(Dataset):
    """A virtual dataset that combines multiple leaf datasets."""

    def __init__(self, name: str, datasets: Iterable[str]):
        super().__init__({"name": name, "title": name})
        self._leaf_names = set(datasets)

    @property
    def dataset_names(self) -> list[str]:
        return [self.name] + list(self._leaf_names)

    @property
    def leaf_names(self) -> set[str]:
        return self._leaf_names


def get_level_store(dataset_names: Iterable[str], fresh: bool = False) -> LevelDBStore:
    """Get a LevelDB store for processing."""
    # Imported here so only the LevelDB commands (xref, dedupe, dedupe-edges,
    # export) need a working plyvel/leveldb install; every other command (crawl,
    # load, release, ...) runs without it.
    from nomenklatura.store.level import LevelDBStore

    if fresh and LEVEL_PATH.exists():
        shutil.rmtree(LEVEL_PATH)

    LEVEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = CombinedDataset("all", dataset_names)
    resolver = get_resolver(begin=True)
    try:
        linker = resolver.get_linker()
    finally:
        resolver.rollback()
    return LevelDBStore(dataset, linker, LEVEL_PATH)


class MergedSQLView(SQLView[DS, SE]):
    """Custom SQL view that properly merges entities with the same canonical_id.

    When querying for an entity by its canonical ID, this view collects ALL statements
    from all entities that were merged into that canonical ID and assembles them into
    a single entity with the most specific schema.
    """

    def get_entity(self, id: str) -> SE | None:
        """Get entity by canonical ID, merging all statements from merged entities."""
        table = self.store.table
        q = select(table)
        q = q.where(table.c.canonical_id == id)
        q = q.where(table.c.dataset.in_(self.dataset_names))
        # Order by entity_id to ensure consistent grouping if needed for debugging,
        # but we'll collect ALL statements regardless
        q = q.order_by(table.c.entity_id)

        # Collect ALL statements with this canonical_id
        all_statements: list[Statement] = []
        for stmt in self.store._iterate_stmts(q, stream=False):
            all_statements.append(stmt)

        if not all_statements:
            return None

        # Assemble into a single entity - from_statements will compute the
        # most specific common schema (e.g., Person over LegalEntity)
        return self.store.assemble(all_statements)


class MergedSQLStore(SQLStore[DS, SE]):
    """Custom SQL store that uses MergedSQLView."""

    def __init__(self, dataset: DS, linker, uri: str = SQL_URI, **engine_kwargs):
        Store.__init__(self, dataset, linker)
        if get_database_dialect(uri) != "sqlite" and "pool_size" not in engine_kwargs:
            engine_kwargs["pool_size"] = nk_settings.DB_POOL_SIZE
        metadata = MetaData()
        self.engine = create_engine(uri, **engine_kwargs)
        self.table = make_statement_table(metadata)
        metadata.create_all(self.engine, tables=[self.table], checkfirst=True)

    def view(self, scope: DS, external: bool = False) -> SQLView[DS, SE]:
        return MergedSQLView(self, scope, external=external)

    def writer(self):
        return MuckrakeSQLWriter(self)


class MuckrakeSQLWriter(SQLWriter[DS, SE]):
    """A writer whose whole session is one transaction.

    nomenklatura's writer already keeps a single transaction open across batches
    until it flushes, but flushes (commits) on exit even when an exception is in
    flight. This one rolls back instead, and ``replace`` deletes inside the same
    transaction, so a delete-then-reload commits completely or not at all.
    """

    # Keep statement batches moderate to avoid oversized INSERT statements.
    BATCH_STATEMENTS = SQL_BATCH_STATEMENTS

    def replace(self, where: Any = None) -> None:
        """Delete statements (all, or those matching ``where``) in this writer's transaction."""
        if self.tx is None:
            self.tx = self.conn.begin()
        query = delete(self.store.table)
        if where is not None:
            query = query.where(where)
        self.conn.execute(query)

    def __exit__(
        self,
        type: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if type is None:
            self.flush()
        elif self.tx is not None:
            self.tx.rollback()
            self.tx = None
        self.conn.close()


def get_sql_store(dataset_names: Iterable[str], uri: str = SQL_URI) -> MergedSQLStore:
    """Get a SQL store for serving with proper entity merging."""
    dataset = CombinedDataset("all", dataset_names)
    resolver = get_resolver(uri=uri, begin=True)
    try:
        linker = resolver.get_linker()
    finally:
        resolver.rollback()
    return MergedSQLStore(dataset, linker, uri=uri)
