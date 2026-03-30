from __future__ import annotations

import logging

from nomenklatura.db import get_engine, get_metadata
from nomenklatura.resolver import Resolver
from nomenklatura.store.sql import make_statement_table
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, text
from sqlalchemy.engine import Engine

from muckrake.settings import SQL_URI

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


def init_database(uri: str = SQL_URI) -> Engine:
    engine = get_engine(uri)
    metadata = get_metadata()
    statement_table = metadata.tables.get("statement")
    if statement_table is None:
        statement_table = make_statement_table(metadata)
    resolver = Resolver(engine, metadata, create=True)
    ner_candidates = get_ner_candidates_table(metadata)
    dataset_runs = get_dataset_runs_table(metadata)
    dataset_run_artifacts = get_dataset_run_artifacts_table(metadata)
    metadata.create_all(
        bind=engine,
        tables=[
            statement_table,
            resolver._table,
            ner_candidates,
            dataset_runs,
            dataset_run_artifacts,
        ],
        checkfirst=True,
    )
    _ensure_ner_candidates_constraints(engine)
    _ensure_dataset_run_constraints(engine)
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
