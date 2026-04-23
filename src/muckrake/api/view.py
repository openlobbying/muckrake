from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from nomenklatura.db import get_engine
from sqlalchemy import text

from muckrake.api.serialization import get_all_datasets_metadata, serialize_entity
from muckrake.dataset import list_dataset_names
from muckrake.settings import PUBLISHED_SQL_URI
from muckrake.store import get_sql_store


@lru_cache(maxsize=1)
def get_published_engine():
    return get_engine(PUBLISHED_SQL_URI)


def _list_db_dataset_names() -> List[str]:
    engine = get_published_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT DISTINCT dataset FROM statement "
                "WHERE dataset IS NOT NULL AND dataset != '' ORDER BY dataset"
            )
        )
        return [row[0] for row in result]


@lru_cache(maxsize=1)
def list_all_dataset_names() -> List[str]:
    names = set(list_dataset_names())
    try:
        names.update(_list_db_dataset_names())
    except Exception:
        pass
    return sorted(names)


def get_view():
    store = get_sql_store(
        list_all_dataset_names(),
        uri=PUBLISHED_SQL_URI,
        engine=get_published_engine(),
    )
    return store.default_view(external=True)


def serialize_view_entity(ent) -> Dict[str, Any]:
    view = get_view()

    def get_entity_details(entity_id: str) -> Dict[str, str]:
        detail = view.get_entity(entity_id)
        if detail is None:
            return {"caption": entity_id, "schema": "Entity"}
        return {"caption": detail.caption, "schema": detail.schema.name}

    return serialize_entity(ent, get_all_datasets_metadata(), get_entity_details)
