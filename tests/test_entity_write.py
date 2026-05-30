from __future__ import annotations

import pytest

from muckrake.entity_write import build_entity, build_entity_spec, parse_properties


def test_parse_properties_requires_key_value():
    with pytest.raises(ValueError, match="Expected KEY=VALUE"):
        parse_properties(["name"])


def test_build_entity_generates_id_and_validates():
    spec = build_entity_spec(
        schema_name="Company",
        dataset="test",
        source_ref="source-1",
        entity_id=None,
        id_parts=["acme-inc"],
        key_prefix=None,
        property_items=["name=ACME Inc"],
    )

    entity = build_entity(spec)

    assert entity.id is not None
    assert entity.schema.name == "Company"
    assert entity.get("name") == ["ACME Inc"]


def test_build_entity_rejects_invalid_property():
    spec = build_entity_spec(
        schema_name="Company",
        dataset="test",
        source_ref="source-1",
        entity_id=None,
        id_parts=[],
        key_prefix=None,
        property_items=["notARealProp=value"],
    )

    with pytest.raises(ValueError):
        build_entity(spec)
