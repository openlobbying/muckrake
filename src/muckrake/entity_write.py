from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from followthemoney import Dataset as FTMDataset
from followthemoney import model as ftm_model
from followthemoney.exc import InvalidData
from followthemoney.statement import Statement
from sqlalchemy import delete, select, update

from muckrake.entity_query import clear_query_caches, get_entity_payload, get_view, list_all_dataset_names
from muckrake.settings import get_working_sql_uri
from muckrake.store import get_sql_store


@dataclass
class EntitySpec:
    schema_name: str
    dataset: str
    source_ref: str
    entity_id: str | None
    id_parts: list[str]
    key_prefix: str | None
    properties: dict[str, list[str]]


def parse_properties(items: list[str]) -> dict[str, list[str]]:
    properties: dict[str, list[str]] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --property value: {item!r}. Expected KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(
                f"Invalid --property value: {item!r}. Property name is empty."
            )
        properties.setdefault(key, []).append(value)

    if not properties:
        raise ValueError("At least one --property is required.")
    return properties


def build_entity_spec(
    *,
    schema_name: str,
    dataset: str,
    source_ref: str,
    entity_id: str | None,
    id_parts: list[str],
    key_prefix: str | None,
    property_items: list[str],
) -> EntitySpec:
    return EntitySpec(
        schema_name=schema_name,
        dataset=dataset,
        source_ref=source_ref,
        entity_id=entity_id,
        id_parts=id_parts,
        key_prefix=key_prefix,
        properties=parse_properties(property_items),
    )


def build_entity(spec: EntitySpec):
    entity = ftm_model.make_entity(spec.schema_name, key_prefix=spec.key_prefix)
    try:
        for prop_name, values in spec.properties.items():
            entity.add(prop_name, values)
    except InvalidData as exc:
        raise ValueError(str(exc)) from exc

    if spec.entity_id:
        entity.id = spec.entity_id
    else:
        parts: list[str] = [spec.schema_name]
        if spec.id_parts:
            parts.extend(spec.id_parts)
        else:
            parts.extend([spec.dataset, spec.source_ref])
            parts.extend(entity.get("name", quiet=True)[:1])
        entity.make_id(*parts)

    entity_dict = entity.to_dict()
    try:
        entity.schema.validate(entity_dict)
    except Exception as exc:
        details = getattr(exc, "errors", None)
        if details is not None:
            raise ValueError(json.dumps(details, indent=2, sort_keys=True)) from exc
        raise
    return entity


def _entity_statements(entity, dataset_name: str, source_ref: str) -> list[Statement]:
    statements: list[Statement] = [
        Statement(
            entity_id=entity.id,
            prop="id",
            schema=entity.schema.name,
            value=entity.id,
            dataset=dataset_name,
            origin=source_ref,
        )
    ]

    for prop_name, values in entity.properties.items():
        for value in values:
            statements.append(
                Statement(
                    entity_id=entity.id,
                    prop=prop_name,
                    schema=entity.schema.name,
                    value=value,
                    dataset=dataset_name,
                    origin=source_ref,
                )
            )
    return statements


def _dataset_title(name: str) -> str:
    return name


def _mark_existing_statements_canonical(store, entity_id: str) -> None:
    with store.engine.begin() as conn:
        conn.execute(
            update(store.table)
            .where(store.table.c.entity_id == entity_id)
            .values(canonical_id=entity_id)
        )


def add_entity(spec: EntitySpec, *, uri: str | None = None) -> dict[str, Any]:
    if uri is None:
        uri = get_working_sql_uri()

    entity = build_entity(spec)
    dataset = FTMDataset.make({"name": spec.dataset, "title": _dataset_title(spec.dataset)})
    store = get_sql_store([spec.dataset], uri=uri)

    with store.engine.begin() as conn:
        existed = (
            conn.execute(
                select(store.table.c.entity_id)
                .where(store.table.c.entity_id == entity.id)
                .limit(1)
            ).first()
            is not None
        )
        conn.execute(delete(store.table).where(store.table.c.entity_id == entity.id))

    _mark_existing_statements_canonical(store, entity.id)

    with store.writer() as writer:
        for statement in _entity_statements(entity, dataset.name, spec.source_ref):
            writer.add_statement(statement)

    clear_query_caches()
    payload = get_entity_payload(entity.id, uri=uri)
    if payload is None:
        raise RuntimeError(f"Failed to read stored entity: {entity.id}")

    return {
        "status": "ok",
        "action": "updated" if existed else "created",
        "entity": payload,
        "provenance": {
            "dataset": spec.dataset,
            "source": spec.source_ref,
            "origin": spec.source_ref,
        },
    }


def update_entity(
    entity_id: str,
    *,
    property_items: list[str],
    dataset: str | None = None,
    source_ref: str | None = None,
    schema_name: str | None = None,
    uri: str | None = None,
) -> dict[str, Any]:
    if uri is None:
        uri = get_working_sql_uri()

    view = get_view(uri)
    existing = view.get_entity(entity_id)
    if existing is None:
        raise ValueError(f"Entity not found: {entity_id}")

    existing_data = existing.to_dict()
    properties = {
        prop_name: [str(value) for value in values]
        for prop_name, values in existing_data.get("properties", {}).items()
    }
    for prop_name, values in parse_properties(property_items).items():
        properties[prop_name] = values

    resolved_dataset = dataset or (sorted(existing.datasets)[0] if existing.datasets else None)
    if resolved_dataset is None:
        raise ValueError("--dataset is required when the existing entity has no dataset")

    resolved_source = source_ref or _get_existing_origin(entity_id, uri=uri)
    if resolved_source is None:
        raise ValueError("--source is required when the existing entity has no origin")

    spec = EntitySpec(
        schema_name=schema_name or existing.schema.name,
        dataset=resolved_dataset,
        source_ref=resolved_source,
        entity_id=entity_id,
        id_parts=[],
        key_prefix=None,
        properties=properties,
    )
    return add_entity(spec, uri=uri)


def _get_existing_origin(entity_id: str, *, uri: str) -> str | None:
    store = get_sql_store(list_all_dataset_names(uri), uri=uri)
    with store.engine.connect() as conn:
        row = conn.execute(
            select(store.table.c.origin)
            .where(store.table.c.canonical_id == entity_id)
            .where(store.table.c.origin.is_not(None))
            .limit(1)
        ).first()
        if row is None:
            row = conn.execute(
                select(store.table.c.origin)
                .where(store.table.c.entity_id == entity_id)
                .where(store.table.c.origin.is_not(None))
                .limit(1)
            ).first()
    if row is None:
        return None
    return str(row[0])
