from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from followthemoney import model
from nomenklatura.db import get_engine
from nomenklatura.judgement import Judgement
from sqlalchemy import text

from muckrake.api.serialization import get_all_datasets_metadata, serialize_entity
from muckrake.dataset import list_dataset_names
from muckrake.settings import BASE_PATH, PUBLISHED_SQL_URI
from muckrake.store import get_resolver, get_sql_store

DEV_ADMIN_SECRET = "openlobbying-dev-auth-secret-change-me"


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value

    return values


@lru_cache(maxsize=1)
def _frontend_env() -> Dict[str, str]:
    return _read_env_file(BASE_PATH / "openlobbying" / ".env")


def get_admin_api_secret() -> str:
    return (
        os.getenv("AUTH_SECRET")
        or os.getenv("BETTER_AUTH_SECRET")
        or _frontend_env().get("AUTH_SECRET")
        or _frontend_env().get("BETTER_AUTH_SECRET")
        or DEV_ADMIN_SECRET
    )


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
def _list_all_dataset_names() -> List[str]:
    names = set(list_dataset_names())
    try:
        names.update(_list_db_dataset_names())
    except Exception:
        pass
    return sorted(names)


@lru_cache(maxsize=1)
def get_view():
    dataset_names = _list_all_dataset_names()
    store = get_sql_store(dataset_names, uri=PUBLISHED_SQL_URI)
    return store.default_view(external=True)


@lru_cache(maxsize=2000)
def _get_entity_details(entity_id: str) -> Dict[str, str]:
    view = get_view()
    ent = view.get_entity(entity_id)
    if ent is None:
        return {"caption": entity_id, "schema": "Entity"}
    return {"caption": ent.caption, "schema": ent.schema.name}


def _serialize(ent) -> Dict[str, Any]:
    return serialize_entity(ent, get_all_datasets_metadata(), _get_entity_details)


def get_next_dedupe_candidate(limit: int = 50) -> Optional[Dict[str, Any]]:
    resolver = get_resolver(begin=True)
    view = get_view()
    try:
        for left_id, right_id, score in resolver.get_candidates(limit=limit):
            left = view.get_entity(left_id)
            right = view.get_entity(right_id)
            if left is None or right is None:
                continue

            left_schema = model.get(left.schema.name)
            right_schema = model.get(right.schema.name)
            route = "profile" if (
                left_schema is not None
                and right_schema is not None
                and left_schema.is_a("LegalEntity")
                and right_schema.is_a("LegalEntity")
            ) else "entity"

            return {
                "left": _serialize(left),
                "right": _serialize(right),
                "score": score,
                "route": route,
            }

        return None
    finally:
        resolver.rollback()


def record_dedupe_judgement(
    left_id: str,
    right_id: str,
    judgement_value: str,
    user: str = "muckrake/web-dedupe",
) -> str:
    try:
        judgement = Judgement(judgement_value)
    except ValueError as exc:
        raise ValueError(f"Invalid judgement: {judgement_value}") from exc

    resolver = get_resolver()
    resolver.begin()
    try:
        if not resolver.check_candidate(left_id, right_id):
            raise ValueError("This candidate has already been judged.")

        canonical = resolver.decide(left_id, right_id, judgement, user=user)
        resolver.commit()
        return str(canonical)
    except Exception:
        resolver.rollback()
        raise