import json
import logging
from pathlib import Path
from typing import Iterator

from followthemoney import model
from followthemoney.statement import Statement
from followthemoney.statement.serialize import read_pack_statements
from sqlalchemy import text

from org_id import make_hashed_id

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

            prelim: list[tuple[str | None, str, str, dict[str, list[str]]]] = []
            key_to_id: dict[str, str] = {}
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

                prefix = (
                    stmt.entity_id.rsplit("-", 1)[0] if "-" in stmt.entity_id else "ner"
                )
                names = clean_props.get("name")
                if names:
                    new_id = make_hashed_id(prefix, names[0])
                else:
                    stable_props = json.dumps(clean_props, sort_keys=True)
                    new_id = make_hashed_id(prefix, schema, stable_props)

                if local_key:
                    key_to_id[local_key] = new_id

                prelim.append((local_key, new_id, schema, clean_props))

            fragments: list[tuple[str, str, dict[str, list[str]]]] = []
            for _, new_id, schema, clean_props in prelim:
                resolved_props: dict[str, list[str]] = {}
                for prop_name, values in clean_props.items():
                    out_values: list[str] = []
                    for value in values:
                        if value.startswith("$ref:"):
                            ref_key = value[5:]
                            ref_id = key_to_id.get(ref_key)
                            if ref_id is None:
                                continue
                            out_values.append(ref_id)
                        else:
                            out_values.append(value)
                    if out_values:
                        resolved_props[prop_name] = out_values

                if resolved_props:
                    fragments.append((new_id, schema, resolved_props))

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
