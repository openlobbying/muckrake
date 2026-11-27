"""Changes a reviewer makes to an extraction: a list of entity dicts, each with a
``schema``, ``properties`` (lists of strings) and an optional ``key`` that other
entities point to with ``$ref:<key>`` values. Every function returns a new list.
"""

from __future__ import annotations

import copy
from typing import Any

from followthemoney import model

Extraction = list[dict[str, Any]]

# The schemas the extraction prompt allows, offered when editing an entity.
EXTRACTION_SCHEMAS = (
    "Person",
    "Company",
    "PublicBody",
    "Organization",
    "LegalEntity",
    "Employment",
    "Ownership",
)
BODY_SCHEMAS = ("PublicBody", "Company", "Organization", "LegalEntity")

# The properties shown when editing an entity of each schema, besides any it has.
FORM_FIELDS = {
    "Person": ("name", "alias", "abbreviation", "title", "position"),
    "Employment": ("employee", "employer", "role"),
    "Ownership": ("owner", "asset", "role"),
}
DEFAULT_FORM_FIELDS = ("name", "alias", "abbreviation")


def validate_extraction(payload: Any) -> None:
    """Raise ``ValueError`` unless ``payload`` has the shape of an extraction."""
    if not isinstance(payload, list):
        raise ValueError("Extraction must be a JSON array")

    for index, entity in enumerate(payload, start=1):
        if not isinstance(entity, dict):
            raise ValueError(f"Entity #{index} must be an object")

        schema = entity.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError(f"Entity #{index} is missing a string 'schema'")

        props = entity.get("properties")
        if not isinstance(props, dict):
            raise ValueError(f"Entity #{index} is missing an object 'properties'")

        for prop_name, values in props.items():
            if not isinstance(prop_name, str):
                raise ValueError(f"Entity #{index} has non-string property name")
            if not isinstance(values, list):
                raise ValueError(f"Entity #{index} property '{prop_name}' must be an array")
            for value in values:
                if not isinstance(value, str):
                    raise ValueError(
                        f"Entity #{index} property '{prop_name}' values must be strings"
                    )


def entity_name(entity: dict[str, Any]) -> str:
    names = [v for v in entity.get("properties", {}).get("name", []) if v.strip()]
    return names[0] if names else "-"


def is_ref_property(schema: str, prop: str) -> bool:
    """Whether ``prop`` on ``schema`` points to another entity."""
    schema_obj = model.get(schema)
    prop_obj = schema_obj.get(prop) if schema_obj is not None else None
    return prop_obj is not None and prop_obj.type.name == "entity"


def form_fields(entity: dict[str, Any]) -> list[str]:
    """The properties to show when editing ``entity``: its schema's, then any others it has."""
    fields = list(FORM_FIELDS.get(entity.get("schema", ""), DEFAULT_FORM_FIELDS))
    fields += [p for p in entity.get("properties", {}) if p not in fields]
    return fields


def describe_ref(extraction: Extraction, value: str) -> str:
    """A ``$ref:<key>`` value as the entity it points to, e.g. "→ Person: Heather Sandy"."""
    key = value[5:]
    for entity in extraction:
        if entity.get("key") == key:
            return f"→ {entity.get('schema')}: {entity_name(entity)}"
    return f"→ ? ({key})"


def with_keys(extraction: Extraction) -> Extraction:
    """A copy where every entity has a key, so any entity can be pointed to."""
    result = copy.deepcopy(extraction)
    used = {entity["key"] for entity in result if entity.get("key")}
    number = 1
    for entity in result:
        if entity.get("key"):
            continue
        while f"k{number}" in used:
            number += 1
        entity["key"] = f"k{number}"
        used.add(entity["key"])
    return result


def replace_entity(extraction: Extraction, index: int, entity: dict[str, Any]) -> Extraction:
    result = copy.deepcopy(extraction)
    result[index] = copy.deepcopy(entity)
    return result


def add_entity(extraction: Extraction, entity: dict[str, Any]) -> Extraction:
    return [*copy.deepcopy(extraction), copy.deepcopy(entity)]


def delete_entity(extraction: Extraction, index: int) -> Extraction:
    """Remove one entity, and every ``$ref`` value that pointed to it."""
    result = copy.deepcopy(extraction)
    removed = result.pop(index)
    key = removed.get("key")
    if key:
        for entity in result:
            props = entity.get("properties", {})
            for prop in list(props):
                props[prop] = [v for v in props[prop] if v != f"$ref:{key}"]
                if not props[prop]:
                    del props[prop]
    return result


def split_entity(
    extraction: Extraction,
    index: int,
    person_name: str,
    body_name: str,
    body_schema: str,
    role: str = "",
) -> Extraction:
    """Replace one entity with a Person, a body and the Employment that links them.

    The entity's key, and so any ``$ref`` to it, moves to the new entity of the same
    kind: the Person if the entity was a Person, the body otherwise.
    """
    keyed = with_keys(extraction)
    old = keyed[index]
    used = {entity["key"] for entity in keyed}

    def new_key(prefix: str) -> str:
        number = 1
        while f"{prefix}{number}" in used:
            number += 1
        used.add(f"{prefix}{number}")
        return f"{prefix}{number}"

    if old.get("schema") == "Person":
        person_key, body_key = old["key"], new_key("b")
    else:
        person_key, body_key = new_key("p"), old["key"]
    employment_props = {"employee": [f"$ref:{person_key}"], "employer": [f"$ref:{body_key}"]}
    if role.strip():
        employment_props["role"] = [role.strip()]
    replacement = [
        {"key": person_key, "schema": "Person", "properties": {"name": [person_name.strip()]}},
        {"key": body_key, "schema": body_schema, "properties": {"name": [body_name.strip()]}},
        {"key": new_key("e"), "schema": "Employment", "properties": employment_props},
    ]
    return keyed[:index] + replacement + keyed[index + 1 :]
