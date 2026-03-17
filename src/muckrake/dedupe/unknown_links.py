import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Optional, Tuple

from followthemoney import Dataset
from followthemoney.statement.entity import StatementEntity
from nomenklatura.db import get_engine, get_metadata
from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Table,
    Unicode,
    UniqueConstraint,
    delete,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError

from muckrake.id import make_hashed_id
from muckrake.settings import SQL_URI

log = logging.getLogger(__name__)


UNKNOWN_LINKS_TABLE = "unknown_links"
UNKNOWN_LINKS_DATASET = "muckrake_links"


@dataclass(frozen=True)
class UnknownLink:
    subject: str
    object: str
    score: Optional[float] = None
    user: Optional[str] = None
    created_at: Optional[str] = None


def _now_ts() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_pair(subject: str, object: str) -> Tuple[str, str]:
    if subject <= object:
        return subject, object
    return object, subject


def _ensure_sqlite_wal(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))


def _apply_sqlite_pragmas(conn) -> None:
    try:
        conn.execute(text("PRAGMA busy_timeout=5000;"))
    except Exception:
        pass


def get_unknown_links_table(
    metadata: MetaData, name: str = UNKNOWN_LINKS_TABLE
) -> Table:
    return Table(
        name,
        metadata,
        Column("id", Integer(), primary_key=True),
        Column("subject", Unicode(512), index=True, nullable=False),
        Column("object", Unicode(512), index=True, nullable=False),
        Column("score", Float, nullable=True),
        Column("user", Unicode(512), nullable=True),
        Column("created_at", Unicode(64), nullable=False),
        UniqueConstraint("subject", "object", name=f"{name}_subject_object_uniq"),
        extend_existing=True,
    )


class UnknownLinksStore:
    def __init__(self, uri: str = SQL_URI, table_name: str = UNKNOWN_LINKS_TABLE):
        self.engine = get_engine(uri)
        self.metadata = get_metadata()
        self.table = get_unknown_links_table(self.metadata, name=table_name)
        self.metadata.create_all(bind=self.engine, tables=[self.table], checkfirst=True)
        _ensure_sqlite_wal(self.engine)

    def add(
        self,
        subject: str,
        object: str,
        score: Optional[float] = None,
        user: Optional[str] = None,
    ) -> bool:
        subject, object = _normalize_pair(subject, object)
        created_at = _now_ts()
        values = {
            "subject": subject,
            "object": object,
            "score": score,
            "user": user,
            "created_at": created_at,
        }
        try:
            with self.engine.begin() as conn:
                if self.engine.dialect.name == "sqlite":
                    _apply_sqlite_pragmas(conn)
                conn.execute(self.table.insert().values(values))
            return True
        except IntegrityError:
            return False

    def iter_links(self) -> Iterable[UnknownLink]:
        stmt = select(
            self.table.c.subject,
            self.table.c.object,
            self.table.c.score,
            self.table.c.user,
            self.table.c.created_at,
        ).order_by(self.table.c.created_at.asc(), self.table.c.id.asc())
        with self.engine.connect() as conn:
            if self.engine.dialect.name == "sqlite":
                _apply_sqlite_pragmas(conn)
            for row in conn.execute(stmt):
                m = row._mapping
                yield UnknownLink(
                    subject=str(m["subject"]),
                    object=str(m["object"]),
                    score=(float(m["score"]) if m["score"] is not None else None),
                    user=(str(m["user"]) if m["user"] is not None else None),
                    created_at=str(m["created_at"]),
                )


def materialize_unknown_links(store) -> int:
    """Write UnknownLink entities into the statement table.

    This is intentionally done at load-time so UI actions can be stored separately
    (in unknown_links) and then materialized into FtM statements for serving.
    """
    links = UnknownLinksStore(uri=str(store.engine.url))

    # Remove previously materialized links so we don't keep stale IDs around
    with store.engine.begin() as conn:
        conn.execute(
            delete(store.table).where(store.table.c.dataset == UNKNOWN_LINKS_DATASET)
        )

    resolver = getattr(store, "linker", None)
    ds = Dataset.make({"name": UNKNOWN_LINKS_DATASET, "title": "Muckrake links"})

    written = 0
    with store.writer() as writer:
        for link in links.iter_links():
            subject = link.subject
            object = link.object
            if resolver is not None:
                subject = resolver.get_canonical(subject)
                object = resolver.get_canonical(object)
            subject, object = _normalize_pair(subject, object)

            ent = StatementEntity(ds, {"schema": "UnknownLink"})
            ent.id = make_hashed_id(UNKNOWN_LINKS_DATASET, subject, object)
            ent.add("subject", subject)
            ent.add("object", object)

            for stmt in ent.statements:
                writer.add_statement(stmt)
            written += 1

    if written:
        log.info("Materialized %s UnknownLink entities", written)
    return written
