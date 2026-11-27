import json
import logging
from collections.abc import Iterator
from pathlib import Path

from followthemoney import model
from followthemoney.statement import Statement
from followthemoney.statement.serialize import read_pack_statements
from org_id import make_hashed_id
from sqlalchemy import text

from .pipeline import text_fingerprint
from .storage import get_connection

log = logging.getLogger(__name__)


def _can_use_replacement(schema_name: str, prop_name: str, target_schema: str) -> bool:
    try:
        schema = model.get(schema_name)
        if schema is None:
            return False
        prop = schema.get(prop_name)
        if prop is None:
            return False
        if prop.type.name != "entity":
            return False
        if prop.range is None:
            return True
        target = model.get(target_schema)
        if target is None:
            return False
        return target.is_a(prop.range)
    except Exception:
        return False


def _clone_statement(stmt: Statement, value: str) -> Statement:
    return Statement(
        entity_id=stmt.entity_id,
        prop=stmt.prop,
        schema=stmt.schema,
        value=value,
        dataset=stmt.dataset,
        lang=stmt.lang,
        original_value=stmt.original_value,
        first_seen=stmt.first_seen,
        external=stmt.external,
        id=None,
        canonical_id=None,
        last_seen=stmt.last_seen,
        origin=stmt.origin,
    )


def load_approved_candidates() -> dict[tuple[str, str], dict]:
    try:
        conn = get_connection()
        rows = conn.execute(
            text(
                """
            SELECT
                property_name,
                fingerprint,
                extraction_json
            FROM ner_candidates
            WHERE status = 'approved'
            ORDER BY updated_at DESC, id DESC
            """
            )
        )
    except Exception:
        return {}

    out: dict[tuple[str, str], dict] = {}
    for row in rows:
        mapping = row._mapping
        key = (mapping["property_name"], mapping["fingerprint"])
        if key in out:
            continue
        try:
            out[key] = json.loads(mapping["extraction_json"])
        except json.JSONDecodeError:
            log.warning(
                "Invalid extraction JSON for %s:%s",
                mapping["property_name"],
                mapping["fingerprint"],
            )
            continue
    conn.close()
    return out


def _resolve_refs(props: dict[str, list[str]], key_to_id: dict[str, str]) -> dict[str, list[str]]:
    """Replace "$ref:<key>" values with the referenced fragment's ID; drop refs to unknown keys."""
    resolved: dict[str, list[str]] = {}
    for prop_name, values in props.items():
        out_values = []
        for value in values:
            if value.startswith("$ref:"):
                ref_id = key_to_id.get(value[5:])
                if ref_id is not None:
                    out_values.append(ref_id)
            else:
                out_values.append(value)
        if out_values:
            resolved[prop_name] = out_values
    return resolved


def build_replacement_plan(
    pack_path: Path, candidates: dict[tuple[str, str], dict]
) -> dict[str, list[tuple[str, str, dict[str, list[str]]]]]:
    replacements: dict[str, list[tuple[str, str, dict[str, list[str]]]]] = {}
    with open(pack_path, "rb") as fh:
        for stmt in read_pack_statements(fh):
            if stmt.prop != "name":
                continue

            key = (stmt.prop, text_fingerprint(stmt.value))
            candidate = candidates.get(key)
            if candidate is None:
                continue

            entities = candidate
            if not isinstance(entities, list) or not entities:
                continue

            prelim: list[tuple[str | None, str, dict[str, list[str]]]] = []
            for fragment in entities:
                schema = fragment.get("schema")
                props = fragment.get("properties")
                if not isinstance(schema, str) or not isinstance(props, dict):
                    continue

                schema_obj = model.get(schema)
                if schema_obj is None:
                    log.warning("Skipping fragment with unknown schema '%s'", schema)
                    continue

                local_key = fragment.get("key")
                if local_key is not None and not isinstance(local_key, str):
                    local_key = None

                clean_props: dict[str, list[str]] = {}
                for prop_name, values in props.items():
                    if not isinstance(prop_name, str) or not isinstance(values, list):
                        continue
                    prop = schema_obj.get(prop_name)
                    if prop is None:
                        log.warning(
                            "Skipping invalid property '%s' for schema '%s'",
                            prop_name,
                            schema,
                        )
                        continue

                    out_values: list[str] = []
                    for value in values:
                        if not isinstance(value, str):
                            continue
                        if value.startswith("$ref:"):
                            if prop.type.name != "entity":
                                continue
                            out_values.append(value)
                            continue
                        cleaned = prop.type.clean(value)
                        if cleaned is None:
                            continue
                        out_values.append(cleaned)

                    if out_values:
                        clean_props[prop_name] = out_values

                prelim.append((local_key, schema, clean_props))

            prefix = stmt.entity_id.rsplit("-", 1)[0] if "-" in stmt.entity_id else "ner"
            # Named fragments are hashed on their name, so the same name gets the
            # same ID wherever it's split out.
            ids: dict[int, str] = {}
            key_to_id: dict[str, str] = {}
            for index, (local_key, _, clean_props) in enumerate(prelim):
                names = clean_props.get("name")
                if names:
                    ids[index] = make_hashed_id(prefix, names[0])
                    if local_key:
                        key_to_id[local_key] = ids[index]
            # Nameless fragments (relationships such as Employment) are hashed on
            # their properties with refs resolved, so "$ref:p1 employed by $ref:o1"
            # from two splits about different people gets two IDs.
            for index, (local_key, schema, clean_props) in enumerate(prelim):
                if index not in ids:
                    resolved = _resolve_refs(clean_props, key_to_id)
                    new_id = make_hashed_id(prefix, schema, json.dumps(resolved, sort_keys=True))
                    ids[index] = new_id
                    if local_key:
                        key_to_id[local_key] = new_id

            fragments: list[tuple[str, str, dict[str, list[str]]]] = []
            for index, (_, schema, clean_props) in enumerate(prelim):
                resolved_props = _resolve_refs(clean_props, key_to_id)
                if resolved_props:
                    fragments.append((ids[index], schema, resolved_props))

            if fragments:
                replacements[stmt.entity_id] = fragments
    return replacements


def iter_transformed_statements(
    pack_path: Path,
    dataset_name: str,
    replacements: dict[str, list[tuple[str, str, dict[str, list[str]]]]],
) -> Iterator[Statement]:
    emitted_new_entities: set[str] = set()

    with open(pack_path, "rb") as fh:
        for stmt in read_pack_statements(fh):
            if stmt.entity_id in replacements:
                continue

            if stmt.prop_type == "entity" and stmt.value in replacements:
                for new_id, new_schema, _ in replacements[stmt.value]:
                    if not _can_use_replacement(stmt.schema, stmt.prop, new_schema):
                        continue
                    yield _clone_statement(stmt, new_id)
                continue

            yield stmt

    for fragments in replacements.values():
        for new_id, schema, properties in fragments:
            if new_id in emitted_new_entities:
                continue
            emitted_new_entities.add(new_id)
            yield Statement(
                entity_id=new_id,
                prop="id",
                schema=schema,
                value=new_id,
                dataset=dataset_name,
            )
            for prop_name, values in properties.items():
                for value in values:
                    yield Statement(
                        entity_id=new_id,
                        prop=prop_name,
                        schema=schema,
                        value=value,
                        dataset=dataset_name,
                    )


def iter_dataset_statements(dataset_name: str, pack_path: Path) -> Iterator[Statement]:
    candidates = load_approved_candidates()
    replacements = build_replacement_plan(pack_path, candidates)

    if replacements:
        log.info(
            "Applying NER replacements for %s entities in %s",
            len(replacements),
            dataset_name,
        )

    yield from iter_transformed_statements(pack_path, dataset_name, replacements)
