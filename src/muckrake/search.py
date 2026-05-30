from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Sequence

from followthemoney import model
from nomenklatura.db import get_engine
from sqlalchemy import text

from muckrake.db import is_postgres_uri, refresh_postgres_search
from muckrake.settings import PUBLISHED_SQL_URI, SQL_URI
from muckrake.view import get_view

ACTOR_SCHEMATA = ("Company", "LegalEntity", "Organization", "Person", "PublicBody")


@dataclass
class SearchResponse:
    results: List[Dict[str, Any]]
    total: int
    offset: int
    limit: int

    @property
    def has_next(self) -> bool:
        return (self.offset + len(self.results)) < self.total


POSTGRES_SEARCH_SQL = text(
    """
    WITH q AS (
        SELECT
            :query AS raw,
            websearch_to_tsquery('simple', unaccent(:query)) AS tsq
    )
    SELECT
        es.id,
        COALESCE(es.display_name, es.id) AS name,
        es.schema AS type,
        similarity(COALESCE(es.display_name, ''), q.raw) AS sim_display,
        word_similarity(q.raw, COALESCE(es.names_text, '')) AS sim_word
    FROM entity_search AS es
    CROSS JOIN q
    WHERE
        (
            (q.tsq != ''::tsquery AND es.tsv @@ q.tsq)
            OR similarity(COALESCE(es.display_name, ''), q.raw) > :similarity
            OR word_similarity(q.raw, COALESCE(es.names_text, '')) > :word_similarity
            OR COALESCE(es.names_text, '') ILIKE ('%' || q.raw || '%')
        )
        AND es.schema = ANY(:schemas)
    ORDER BY
        (lower(COALESCE(es.display_name, '')) = lower(q.raw)) DESC,
        (COALESCE(es.display_name, '') ILIKE (q.raw || '%')) DESC,
        ts_rank_cd(es.tsv, q.tsq) DESC,
        GREATEST(
            similarity(COALESCE(es.display_name, ''), q.raw),
            word_similarity(q.raw, COALESCE(es.names_text, ''))
        ) DESC,
        length(COALESCE(es.display_name, es.id)) ASC
    LIMIT :limit OFFSET :offset
    """
)

POSTGRES_SEARCH_COUNT_SQL = text(
    """
    WITH q AS (
        SELECT
            :query AS raw,
            websearch_to_tsquery('simple', unaccent(:query)) AS tsq
    )
    SELECT COUNT(*) AS total
    FROM entity_search AS es
    CROSS JOIN q
    WHERE
        (
            (q.tsq != ''::tsquery AND es.tsv @@ q.tsq)
            OR similarity(COALESCE(es.display_name, ''), q.raw) > :similarity
            OR word_similarity(q.raw, COALESCE(es.names_text, '')) > :word_similarity
            OR COALESCE(es.names_text, '') ILIKE ('%' || q.raw || '%')
        )
        AND es.schema = ANY(:schemas)
    """
)

ACTOR_SITEMAP_IDS_SQL = text(
    """
    SELECT id
    FROM entity_search
    WHERE schema = ANY(:schemas)
    ORDER BY id
    LIMIT :limit OFFSET :offset
    """
)

ACTOR_SITEMAP_COUNT_SQL = text(
    """
    SELECT COUNT(*) AS total
    FROM entity_search
    WHERE schema = ANY(:schemas)
    """
)

ACTOR_COUNTS_SQL = text(
    """
    SELECT schema, COUNT(*) AS count
    FROM entity_search
    WHERE schema = ANY(:schemas)
    GROUP BY schema
    """
)


def refresh_search_index(uri: str = SQL_URI) -> None:
    refresh_postgres_search(uri)


@lru_cache(maxsize=4)
def postgres_search_ready(uri: str = PUBLISHED_SQL_URI) -> bool:
    if not is_postgres_uri(uri):
        return False

    try:
        engine = get_engine(uri)
        with engine.connect() as conn:
            relation = conn.execute(text("SELECT to_regclass('public.entity_search')")).scalar()
            return relation is not None
    except Exception:
        return False


def _include_schema(schema_names: Sequence[str]):
    include_schema = []
    for schema_name in schema_names:
        schema_obj = model.get(schema_name)
        if schema_obj is not None:
            include_schema.append(schema_obj)
    return include_schema


def _view_search(query: str, schema_filter: Sequence[str], limit: int, offset: int) -> SearchResponse:
    view = get_view()
    matched = []
    seen_ids = set()
    query_lower = query.lower()

    for ent in view.entities(include_schemata=_include_schema(schema_filter)):
        if ent.id in seen_ids:
            continue
        if query_lower in ent.caption.lower():
            matched.append({"id": ent.id, "name": ent.caption, "type": ent.schema.name})
            seen_ids.add(ent.id)

    total = len(matched)
    return SearchResponse(
        results=matched[offset : offset + limit],
        total=total,
        offset=offset,
        limit=limit,
    )


def search_entities(
    query: str,
    schema_filter: Sequence[str],
    limit: int,
    offset: int,
    *,
    uri: str = PUBLISHED_SQL_URI,
) -> SearchResponse:
    if postgres_search_ready(uri):
        engine = get_engine(uri)
        with engine.connect() as conn:
            total = conn.execute(
                POSTGRES_SEARCH_COUNT_SQL,
                {
                    "query": query,
                    "similarity": 0.25,
                    "word_similarity": 0.55,
                    "schemas": list(schema_filter),
                },
            ).scalar()
            rows = conn.execute(
                POSTGRES_SEARCH_SQL,
                {
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "similarity": 0.25,
                    "word_similarity": 0.55,
                    "schemas": list(schema_filter),
                },
            )
            results = []
            for row in rows:
                item = dict(row._mapping)
                item.pop("sim_display", None)
                item.pop("sim_word", None)
                results.append(item)
        return SearchResponse(
            results=results,
            total=int(total or 0),
            offset=offset,
            limit=limit,
        )

    return _view_search(query, schema_filter, limit, offset)


def list_actor_sitemap_entries(
    schema_filter: Sequence[str],
    limit: int,
    offset: int,
    *,
    uri: str = PUBLISHED_SQL_URI,
) -> SearchResponse:
    if postgres_search_ready(uri):
        engine = get_engine(uri)
        with engine.connect() as conn:
            total = conn.execute(
                ACTOR_SITEMAP_COUNT_SQL,
                {"schemas": list(schema_filter)},
            ).scalar()
            rows = conn.execute(
                ACTOR_SITEMAP_IDS_SQL,
                {
                    "schemas": list(schema_filter),
                    "limit": limit,
                    "offset": offset,
                },
            )
            results = [
                {"id": str(row._mapping["id"]), "path": f"/profile/{row._mapping['id']}"}
                for row in rows
            ]
        return SearchResponse(
            results=results,
            total=int(total or 0),
            offset=offset,
            limit=limit,
        )

    view = get_view()
    results = []
    seen_ids = set()
    total = 0
    for ent in view.entities(include_schemata=_include_schema(schema_filter)):
        if ent.id in seen_ids:
            continue
        seen_ids.add(ent.id)
        total += 1
        if total <= offset:
            continue
        if len(results) >= limit:
            continue
        results.append({"id": ent.id, "path": f"/profile/{ent.id}"})

    return SearchResponse(results=results, total=total, offset=offset, limit=limit)


def get_actor_schema_counts(
    schema_filter: Iterable[str] = ACTOR_SCHEMATA,
    *,
    uri: str = PUBLISHED_SQL_URI,
) -> Dict[str, int]:
    schema_names = list(schema_filter)
    counts = {schema: 0 for schema in schema_names}

    if postgres_search_ready(uri):
        engine = get_engine(uri)
        with engine.connect() as conn:
            rows = conn.execute(ACTOR_COUNTS_SQL, {"schemas": schema_names})
            for row in rows:
                schema_name = str(row._mapping["schema"])
                counts[schema_name] = int(row._mapping["count"])
        return counts

    view = get_view()
    for ent in view.entities(include_schemata=_include_schema(schema_names)):
        if ent.schema.name in counts:
            counts[ent.schema.name] += 1
    return counts
