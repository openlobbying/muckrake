from __future__ import annotations

import logging

from nomenklatura.db import get_engine, get_metadata
from nomenklatura.resolver import Resolver
from nomenklatura.store.sql import make_statement_table
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, text
from sqlalchemy.engine import Engine

from muckrake.settings import PUBLISHED_SQL_URI, SQL_URI

log = logging.getLogger(__name__)


def get_ner_candidates_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "ner_candidates",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("dataset", String(), nullable=False),
        Column("entity_id", String(), nullable=False),
        Column("schema", String(), nullable=False),
        Column("property_name", String(), nullable=False),
        Column("source_text", Text(), nullable=False),
        Column("fingerprint", String(), nullable=False),
        Column("extractor", String(), nullable=False),
        Column("extractor_version", String(), nullable=False),
        Column("status", String(), nullable=False),
        Column("reviewer", String(), nullable=True),
        Column("reviewed_at", String(), nullable=True),
        Column("extraction_json", Text(), nullable=False),
        Column("created_at", String(), nullable=False),
        Column("updated_at", String(), nullable=False),
        extend_existing=True,
    )


def get_dataset_runs_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "dataset_runs",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("dataset_name", String(), nullable=False),
        Column("run_type", String(), nullable=False),
        Column("status", String(), nullable=False),
        Column("triggered_by", String(), nullable=True),
        Column("code_version", String(), nullable=True),
        Column("config_version", String(), nullable=True),
        Column("run_key", String(), nullable=True),
        Column("error_message", Text(), nullable=True),
        Column("stats_json", Text(), nullable=True),
        Column("started_at", String(), nullable=False),
        Column("finished_at", String(), nullable=True),
        extend_existing=True,
    )


def get_dataset_run_artifacts_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "dataset_run_artifacts",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("dataset_run_id", Integer(), nullable=False),
        Column("artifact_type", String(), nullable=False),
        Column("storage_backend", String(), nullable=False),
        Column("storage_key", String(), nullable=False),
        Column("content_type", String(), nullable=True),
        Column("sha256", String(), nullable=False),
        Column("size_bytes", Integer(), nullable=False),
        Column("metadata_json", Text(), nullable=True),
        Column("created_at", String(), nullable=False),
        extend_existing=True,
    )


def get_releases_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "releases",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("status", String(), nullable=False),
        Column("triggered_by", String(), nullable=True),
        Column("code_version", String(), nullable=True),
        Column("notes", Text(), nullable=True),
        Column("error_message", Text(), nullable=True),
        Column("created_at", String(), nullable=False),
        Column("finished_at", String(), nullable=True),
        Column("published_at", String(), nullable=True),
        extend_existing=True,
    )


def get_resolver_lock_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "resolver_lock",
        metadata,
        Column("pair_key", String(), primary_key=True),
        Column("left_id", String(), nullable=False),
        Column("right_id", String(), nullable=False),
        Column("user_id", String(), nullable=False),
        Column("user_name", String(), nullable=True),
        Column("locked_at", String(), nullable=False),
        Column("expires_at", String(), nullable=False),
        Column("updated_at", String(), nullable=False),
        extend_existing=True,
    )


def get_release_inputs_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "release_inputs",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("release_id", Integer(), nullable=False),
        Column("dataset_run_id", Integer(), nullable=False),
        Column("dataset_name", String(), nullable=False),
        extend_existing=True,
    )


def get_release_artifacts_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    return Table(
        "release_artifacts",
        metadata,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("release_id", Integer(), nullable=False),
        Column("artifact_type", String(), nullable=False),
        Column("storage_backend", String(), nullable=False),
        Column("storage_key", String(), nullable=False),
        Column("content_type", String(), nullable=True),
        Column("sha256", String(), nullable=False),
        Column("size_bytes", Integer(), nullable=False),
        Column("metadata_json", Text(), nullable=True),
        Column("created_at", String(), nullable=False),
        extend_existing=True,
    )


def get_statement_table(metadata: MetaData | None = None) -> Table:
    metadata = metadata or get_metadata()
    table = metadata.tables.get("statement")
    if table is None:
        table = make_statement_table(metadata)
    return table


def init_database(uri: str = SQL_URI) -> Engine:
    engine = get_engine(uri)
    metadata = MetaData()
    statement_table = get_statement_table(metadata)
    resolver = Resolver(engine, metadata, create=True)
    ner_candidates = get_ner_candidates_table(metadata)
    dataset_runs = get_dataset_runs_table(metadata)
    dataset_run_artifacts = get_dataset_run_artifacts_table(metadata)
    releases = get_releases_table(metadata)
    resolver_lock = get_resolver_lock_table(metadata)
    release_inputs = get_release_inputs_table(metadata)
    release_artifacts = get_release_artifacts_table(metadata)
    metadata.create_all(
        bind=engine,
        tables=[
            statement_table,
            ner_candidates,
            dataset_runs,
            dataset_run_artifacts,
            releases,
            resolver_lock,
            release_inputs,
            release_artifacts,
        ],
        checkfirst=True,
    )
    _ensure_ner_candidates_constraints(engine)
    _ensure_dataset_run_constraints(engine)
    _ensure_release_constraints(engine)
    _ensure_resolver_lock_constraints(engine)
    _sync_postgres_sequences(
        engine,
        [
            resolver._table,
            ner_candidates,
            dataset_runs,
            dataset_run_artifacts,
            releases,
            release_inputs,
            release_artifacts,
        ],
    )
    return engine


def ensure_resolver_lock_schema(uri: str = SQL_URI) -> Engine:
    engine = get_engine(uri)
    metadata = MetaData()
    _ = Resolver(engine, metadata, create=True)
    resolver_lock = get_resolver_lock_table(metadata)
    metadata.create_all(bind=engine, tables=[resolver_lock], checkfirst=True)
    _ensure_resolver_lock_constraints(engine)
    return engine


def init_published_database(uri: str = PUBLISHED_SQL_URI) -> Engine:
    engine = get_engine(uri)
    metadata = MetaData()
    statement_table = get_statement_table(metadata)
    resolver = Resolver(engine, metadata, create=True)
    metadata.create_all(
        bind=engine,
        tables=[statement_table],
        checkfirst=True,
    )
    _sync_postgres_sequences(engine, [resolver._table])
    return engine


def refresh_postgres_search(uri: str = SQL_URI) -> None:
    engine = get_engine(uri)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS entity_search"))
        conn.execute(
            text(
                """
                CREATE MATERIALIZED VIEW entity_search AS
                SELECT
                  s.canonical_id AS id,
                  MIN(CASE WHEN s.prop = 'name' THEN s.value END) AS display_name,
                  MIN(s.schema) AS schema,
                  string_agg(DISTINCT s.value, ' ')
                    FILTER (WHERE s.prop IN ('name', 'alias', 'previousName', 'weakAlias', 'abbreviation'))
                    AS names_text,
                  to_tsvector(
                    'simple',
                    unaccent(
                      COALESCE(
                        string_agg(DISTINCT s.value, ' ')
                          FILTER (WHERE s.prop IN ('name', 'alias', 'previousName', 'weakAlias', 'abbreviation')),
                        ''
                      )
                    )
                  ) AS tsv
                FROM statement AS s
                WHERE s.schema IN ('Company', 'LegalEntity', 'Organization', 'Person', 'PublicBody')
                  AND s.canonical_id IS NOT NULL
                GROUP BY s.canonical_id
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS entity_search_id_idx ON entity_search (id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS entity_search_tsv_idx ON entity_search USING GIN (tsv)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS entity_search_display_name_trgm_idx "
                "ON entity_search USING GIN (display_name gin_trgm_ops)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS entity_search_names_text_trgm_idx "
                "ON entity_search USING GIN (names_text gin_trgm_ops)"
            )
        )


def _ensure_ner_candidates_constraints(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ner_candidates_unique_key
                ON ner_candidates(
                    dataset, entity_id, property_name, fingerprint, extractor, extractor_version
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ner_candidates_lookup
                ON ner_candidates(dataset, status, updated_at)
                """
            )
        )


def _ensure_dataset_run_constraints(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS dataset_runs_lookup
                ON dataset_runs(dataset_name, status, started_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS dataset_run_artifacts_unique_key
                ON dataset_run_artifacts(dataset_run_id, artifact_type, storage_key)
                """
            )
        )


def _ensure_release_constraints(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS releases_status_created_at
                ON releases(status, created_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS release_inputs_unique_run
                ON release_inputs(release_id, dataset_run_id)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS release_artifacts_unique_key
                ON release_artifacts(release_id, artifact_type, storage_key)
                """
            )
        )


def _ensure_resolver_lock_constraints(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS resolver_lock_user_expires_at
                ON resolver_lock(user_id, expires_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS resolver_lock_expires_at
                ON resolver_lock(expires_at)
                """
            )
        )


def _sync_postgres_sequences(engine: Engine, tables: list[Table]) -> None:
    if engine.dialect.name not in ("postgresql", "postgres"):
        raise RuntimeError(
            f"Postgres database required, got unsupported dialect: {engine.dialect.name}"
        )

    with engine.begin() as conn:
        for table in tables:
            if "id" not in table.c:
                continue
            table_name = table.name
            conn.execute(
                text(
                    """
                    SELECT setval(
                        pg_get_serial_sequence(:table_name, 'id'),
                        COALESCE((SELECT MAX(id) FROM """
                    + table_name
                    + """), 1),
                        (SELECT COUNT(*) > 0 FROM """
                    + table_name
                    + """)
                    )
                    """
                ),
                {"table_name": table_name},
            )
