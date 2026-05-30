from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Sequence

from followthemoney import model
from nomenklatura.db import get_engine
from sqlalchemy import text

from muckrake.dataset import list_dataset_names
from muckrake.serialize import get_all_datasets_metadata, serialize_entity
from muckrake.settings import PUBLISHED_SQL_URI, SQL_URI, get_working_sql_uri
from muckrake.store import get_sql_store


def normalize_schema_filter(schema_names: Sequence[str]) -> list[str]:
    if not schema_names:
        return []

    normalized: list[str] = []
    seen = set()
    for schema_name in schema_names:
        schema_obj = model.get(schema_name)
        if schema_obj is None:
            if schema_name not in seen:
                normalized.append(schema_name)
                seen.add(schema_name)
            continue

        for candidate in [schema_obj.name, *[child.name for child in schema_obj.descendants]]:
            if candidate not in seen:
                normalized.append(candidate)
                seen.add(candidate)
    return normalized


def _list_db_dataset_names(uri: str) -> list[str]:
    engine = get_engine(uri)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT DISTINCT dataset FROM statement "
                "WHERE dataset IS NOT NULL AND dataset != '' ORDER BY dataset"
            )
        )
        return [row[0] for row in result]


@lru_cache(maxsize=8)
def list_all_dataset_names(uri: str = PUBLISHED_SQL_URI) -> list[str]:
    names = set(list_dataset_names())
    try:
        names.update(_list_db_dataset_names(uri))
    except Exception:
        pass
    return sorted(names)


@lru_cache(maxsize=8)
def get_view(uri: str = PUBLISHED_SQL_URI):
    store = get_sql_store(list_all_dataset_names(uri), uri=uri)
    return store.default_view(external=True)


@lru_cache(maxsize=16000)
def get_entity_details(entity_id: str, uri: str = PUBLISHED_SQL_URI) -> Dict[str, str]:
    view = get_view(uri)
    ent = view.get_entity(entity_id)
    if ent is None:
        return {"caption": entity_id, "schema": "Entity"}
    return {"caption": ent.caption, "schema": ent.schema.name}


def serialize_view_entity(ent, *, uri: str = PUBLISHED_SQL_URI) -> Dict[str, Any]:
    return serialize_entity(
        ent,
        get_all_datasets_metadata(),
        lambda entity_id: get_entity_details(entity_id, uri),
    )


def get_entity_payload(entity_id: str, *, uri: str | None = None) -> Dict[str, Any] | None:
    if uri is None:
        uri = get_working_sql_uri()
    view = get_view(uri)
    ent = view.get_entity(entity_id)
    if ent is None:
        return None
    return serialize_view_entity(ent, uri=uri)


def search_entity_payload(
    query: str,
    schema_filter: Sequence[str],
    limit: int,
    offset: int,
    *,
    uri: str | None = None,
) -> Any:
    from muckrake.search import search_entities as run_search_entities

    if uri is None:
        uri = get_working_sql_uri()

    effective_schema_filter = normalize_schema_filter(schema_filter)
    if not effective_schema_filter:
        effective_schema_filter = [schema.name for schema in model.schemata.values()]
    return run_search_entities(query, effective_schema_filter, limit, offset, uri=uri)


def clear_query_caches() -> None:
    list_all_dataset_names.cache_clear()
    get_view.cache_clear()
    get_entity_details.cache_clear()
