from typing import Any, Dict
from followthemoney import model
from followthemoney.types import registry
from functools import lru_cache

from muckrake.dataset import find_datasets, get_dataset_config, load_raw_config
from muckrake.settings import ACTOR_SCHEMATA
from muckrake.util import parse_date_token


@lru_cache(maxsize=1)
def get_all_datasets_metadata() -> Dict[str, Dict[str, Any]]:
    """Load all dataset configurations."""
    datasets = {}

    for config_path in find_datasets():
        raw = load_raw_config(config_path)
        cfg = get_dataset_config(raw)
        name = cfg.get("name")
        if not name:
            continue

        publisher = (
            raw.get("publisher", {})
            if isinstance(raw.get("publisher", {}), dict)
            else {}
        )
        licence = (
            cfg.get("licence", {}) if isinstance(cfg.get("licence", {}), dict) else {}
        )
        coverage = (
            raw.get("coverage", {}) if isinstance(raw.get("coverage", {}), dict) else {}
        )

        datasets[name] = {
            "name": name,
            "prefix": cfg.get("prefix"),
            "title": cfg.get("title", name),
            "summary": cfg.get("summary"),
            "tags": cfg.get("tags", []),
            "url": cfg.get("url") or cfg.get("index_url"),
            "index_url": cfg.get("index_url"),
            "publisher": {
                "name": publisher.get("name"),
                "description": publisher.get("description"),
                "url": publisher.get("url"),
                "country": publisher.get("country"),
                "country_label": publisher.get("country_label"),
                "official": publisher.get("official"),
            },
            "licence": {
                "name": licence.get("name"),
                "url": licence.get("url"),
            },
            "coverage": {
                "countries": coverage.get("countries", []),
                "frequency": coverage.get("frequency"),
            },
        }

    return datasets


def is_actor(schema_name: str) -> bool:
    """Check if a schema should be treated as an actor profile."""
    schema = model.get(schema_name)
    return schema is not None and any(schema.is_a(s) for s in ACTOR_SCHEMATA)


def _collapse_edge_temporal_extent(data: Dict[str, Any]) -> None:
    if data.get("schema") != "Representation":
        return

    props = data.get("properties", {})
    starts = [v for v in props.get("startDate", []) if isinstance(v, str)]
    ends = [v for v in props.get("endDate", []) if isinstance(v, str)]
    if len(starts) <= 1 and len(ends) <= 1:
        return

    start_tokens = []
    end_tokens = []
    for token in starts:
        parsed = parse_date_token(token, is_end=False)
        if parsed is not None:
            start_tokens.append((parsed, token))
    for token in ends:
        parsed = parse_date_token(token, is_end=True)
        if parsed is not None:
            end_tokens.append((parsed, token))

    if start_tokens:
        start_tokens.sort(key=lambda item: item[0])
        props["startDate"] = [start_tokens[0][1]]
    if end_tokens:
        end_tokens.sort(key=lambda item: item[0], reverse=True)
        props["endDate"] = [end_tokens[0][1]]


def serialize_entity(ent, ds_meta: Dict[str, Any], get_details_fn) -> Dict[str, Any]:
    """Serialize a FollowTheMoney entity object to a simple dict."""
    data = ent.to_dict()
    data["caption"] = ent.caption
    data["canonical_id"] = ent.id

    # Enrich datasets with metadata
    datasets = []
    for ds_name in ent.datasets:
        datasets.append(ds_meta.get(ds_name, {"name": ds_name, "title": ds_name}))
    data["datasets"] = datasets

    # Resolve entity references to include captions for the UI
    for prop, values in data.get("properties", {}).items():
        p = ent.schema.get(prop)
        if p and p.type == registry.entity:
            enriched = []
            for val in values:
                details = get_details_fn(val)
                enriched.append(
                    {
                        "id": val,
                        "caption": details["caption"],
                        "schema": details["schema"],
                    }
                )
            data["properties"][prop] = enriched

    _collapse_edge_temporal_extent(data)

    return data
