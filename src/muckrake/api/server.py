from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from followthemoney import model
from functools import lru_cache
from nomenklatura.resolver import Identifier
from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select, text

from muckrake.logging import configure_logging
from muckrake.api.view import (
    get_published_engine,
    get_view,
    list_all_dataset_names,
    serialize_view_entity,
)
from muckrake.dedupe import (
    DedupeLockError,
    get_lock_engine,
    get_next_dedupe_candidate,
    get_next_dedupe_cluster,
    record_dedupe_cluster_judgement,
    record_dedupe_judgement,
    skip_dedupe_cluster,
)
from muckrake.dedupe.cluster import LockedPair
from muckrake.api.serialization import (
    is_actor,
    get_all_datasets_metadata,
)
from muckrake.api.graph_logic import get_entity_graph_data
from muckrake.settings import ACTOR_SCHEMATA

log = logging.getLogger(__name__)

DEV_ADMIN_SECRET = "openlobbying-dev-auth-secret-change-me"

app = FastAPI(title="Muckrake API", version="0.1.0")
configure_logging(app=app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_admin_api_secret() -> str:
    return os.getenv("BETTER_AUTH_SECRET") or DEV_ADMIN_SECRET


def _schema_filter_values(schema_name: str) -> set[str]:
    schema_obj = model.get(schema_name)
    if schema_obj is None:
        return {schema_name}
    return {child.name for child in schema_obj.descendants} | {schema_obj.name}


def _adjacent_prop_rank(ent, prop_name: str) -> tuple[int, str]:
    if ent.schema.is_a("Payment"):
        payment_ranks = {
            "paymentPayer": 0,
            "paymentBeneficiary": 1,
        }
        if prop_name in payment_ranks:
            return payment_ranks[prop_name], prop_name
    if ent.schema.is_a("Event"):
        event_ranks = {
            "eventsInvolved": 10,
            "eventsOrganized": 11,
        }
        if prop_name in event_ranks:
            return event_ranks[prop_name], prop_name
    return 100, prop_name


PROFILE_ACTIVITY_DEFAULT_LIMIT = 20
PROFILE_ACTIVITY_MAX_LIMIT = 100
PROFILE_ACTIVITY_SCHEMATA = {
    "Event",
    "Meeting",
    "Hospitality",
    "Trip",
    "Representation",
    "Payment",
    "Donation",
    "Gift",
    "Ownership",
    "Directorship",
    "Family",
    "UnknownLink",
    "PublicDisclosure",
}
PROFILE_RELATIONSHIP_SCHEMATA = {"Employment", "Membership", "Representation"}
PROFILE_ACTIVITY_DATE_PROPS = (
    "date",
    "startDate",
    "endDate",
    "incorporationDate",
    "registrationDate",
    "created_at",
    "publishedAt",
)


def _normalize_profile_activity_pagination(
    limit: int, offset: int
) -> tuple[int, int]:
    return max(1, min(limit, PROFILE_ACTIVITY_MAX_LIMIT)), max(0, offset)


def _is_profile_activity_entity(ent) -> bool:
    return ent.schema.name in PROFILE_ACTIVITY_SCHEMATA


def _is_profile_relationship_entity(ent) -> bool:
    return ent.schema.name in PROFILE_RELATIONSHIP_SCHEMATA


def _get_profile_activity_sort_value(ent) -> tuple[str, str]:
    for prop_name in PROFILE_ACTIVITY_DATE_PROPS:
        for value in ent.get(prop_name):
            if isinstance(value, str) and value:
                return value, ent.id
    return "", ent.id


def _collect_profile_adjacent(ent) -> List[tuple[str, Any, tuple[int, str]]]:
    unique_adjacent: dict[str, tuple[str, Any, tuple[int, str]]] = {}
    for prop, adj_ent in view.get_adjacent(ent):
        rank = _adjacent_prop_rank(adj_ent, prop.name)
        existing = unique_adjacent.get(adj_ent.id)
        if existing is None or rank < existing[2]:
            unique_adjacent[adj_ent.id] = (prop.name, adj_ent, rank)
    return list(unique_adjacent.values())


def _get_profile_lookup_ids(entity_id: str) -> List[str]:
    ids = [identifier.id for identifier in view.store.linker.connected(Identifier.get(entity_id))]
    return ids or [entity_id]


def _get_profile_statement_query_parts(
    entity_id: str, schema_names: Optional[set[str]] = None
):
    table = view.store.table
    filters = [
        table.c.prop_type == "entity",
        table.c.value.in_(_get_profile_lookup_ids(entity_id)),
        table.c.dataset.in_(view.dataset_names),
        table.c.canonical_id.is_not(None),
    ]
    if schema_names is not None:
        filters.append(table.c.schema.in_(sorted(schema_names)))
    return table, filters


def _get_profile_activity_sort_expression(table):
    return func.coalesce(
        *[
            func.max(case((table.c.prop == prop_name, table.c.value), else_=None))
            for prop_name in PROFILE_ACTIVITY_DATE_PROPS
        ],
        "",
    )


def _get_profile_adjacent_rank(adj_ent, entity_id: str) -> tuple[int, str]:
    ranks = []
    seen = set()
    for prop, value in adj_ent.itervalues():
        if value != entity_id or prop.reverse is None:
            continue
        prop_name = prop.reverse.name
        if prop_name in seen:
            continue
        seen.add(prop_name)
        ranks.append(_adjacent_prop_rank(adj_ent, prop_name))
    if ranks:
        return min(ranks)
    return 100, adj_ent.schema.name


def _load_profile_relationship_items(entity_id: str) -> List[tuple[str, Any, tuple[int, str]]]:
    table, filters = _get_profile_statement_query_parts(
        entity_id, PROFILE_RELATIONSHIP_SCHEMATA
    )
    query = select(table.c.canonical_id).where(*filters).group_by(table.c.canonical_id)

    with view.store.engine.connect() as conn:
        relationship_ids = [
            str(canonical_id)
            for canonical_id in conn.execute(query).scalars().all()
            if canonical_id is not None
        ]

    items: List[tuple[str, Any, tuple[int, str]]] = []
    for relationship_id in relationship_ids:
        adj_ent = view.get_entity(relationship_id)
        if adj_ent is None:
            continue
        rank = _get_profile_adjacent_rank(adj_ent, entity_id)
        items.append((rank[1], adj_ent, rank))
    return items


def _has_profile_inverted_adjacent(entity_id: str) -> bool:
    table, filters = _get_profile_statement_query_parts(entity_id)
    query = select(table.c.canonical_id).where(*filters).limit(1)
    with view.store.engine.connect() as conn:
        return conn.execute(query).first() is not None


def _has_profile_direct_adjacent(ent) -> bool:
    for prop, _ in ent.itervalues():
        if prop.type.name == "entity":
            return True
    return False


def _serialize_profile_relationships(
    items: List[tuple[str, Any, tuple[int, str]]],
) -> Dict[str, Dict[str, Any]]:
    adjacent: Dict[str, Dict[str, Any]] = {}
    for prop_name, adj_ent, _ in items:
        if not _is_profile_relationship_entity(adj_ent):
            continue

        if prop_name not in adjacent:
            adjacent[prop_name] = {"results": [], "total": 0}
        adjacent[prop_name]["results"].append(serialize_view_entity(adj_ent))
        adjacent[prop_name]["total"] += 1
    return adjacent


def _paginate_profile_activities(
    items: List[tuple[str, Any, tuple[int, str]]],
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    activities = [adj_ent for _, adj_ent, _ in items if _is_profile_activity_entity(adj_ent)]
    activities.sort(key=_get_profile_activity_sort_value, reverse=True)

    total = len(activities)
    paged = activities[offset : offset + limit]

    return {
        "results": [serialize_view_entity(adj_ent) for adj_ent in paged],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_next": (offset + len(paged)) < total,
    }


def _paginate_profile_activities_sql(entity_id: str, limit: int, offset: int) -> Dict[str, Any]:
    table, filters = _get_profile_statement_query_parts(entity_id, PROFILE_ACTIVITY_SCHEMATA)
    sort_expr = _get_profile_activity_sort_expression(table)

    count_query = select(func.count(distinct(table.c.canonical_id))).where(*filters)
    page_query = (
        select(table.c.canonical_id)
        .where(*filters)
        .group_by(table.c.canonical_id)
        .order_by(sort_expr.desc(), table.c.canonical_id.desc())
        .limit(limit)
        .offset(offset)
    )

    with view.store.engine.connect() as conn:
        total = int(conn.execute(count_query).scalar() or 0)
        activity_ids = [
            str(canonical_id)
            for canonical_id in conn.execute(page_query).scalars().all()
            if canonical_id is not None
        ]

    results = []
    for activity_id in activity_ids:
        adj_ent = view.get_entity(activity_id)
        if adj_ent is None:
            continue
        results.append(serialize_view_entity(adj_ent))

    return {
        "results": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_next": (offset + len(results)) < total,
    }


@app.on_event("startup")
def ensure_admin_dedupe_schema() -> None:
    get_lock_engine()


view = get_view()

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


STATS_CACHE_TTL_SECONDS = 600
_stats_cache: Dict[str, Any] = {"expires_at": 0.0, "value": None}


TOP_ACTOR_SQL = text(
    """
    WITH resolved_refs AS (
        SELECT
            COALESCE(r.target, s.value) AS actor_id,
            COALESCE(s.canonical_id, s.entity_id) AS relation_id
        FROM statement s
        LEFT JOIN resolver r
            ON r.source = s.value
            AND r.judgement = 'positive'
        WHERE s.prop_type = 'entity'
    ),
    counts AS (
        SELECT actor_id, COUNT(DISTINCT relation_id) AS connections
        FROM resolved_refs
        WHERE actor_id IS NOT NULL AND relation_id IS NOT NULL
        GROUP BY actor_id
    ),
    actor_base AS (
        SELECT
            s.canonical_id AS actor_id,
            MAX(CASE WHEN s.prop = 'name' THEN s.value END) AS name,
            MAX(s.schema) AS schema,
            MAX(CASE WHEN s.prop = 'topics' AND s.value = 'role.lobby' THEN 1 ELSE 0 END) AS is_lobby,
            MAX(CASE WHEN s.prop = 'topics' AND s.value = 'pol.party' THEN 1 ELSE 0 END) AS is_party
        FROM statement s
        WHERE s.schema IN ('Organization', 'Company', 'LegalEntity', 'Person', 'PublicBody')
        GROUP BY s.canonical_id
    )
    SELECT
        c.actor_id AS id,
        COALESCE(a.name, c.actor_id) AS name,
        a.schema AS schema,
        c.connections AS connections,
        a.is_lobby AS is_lobby,
        a.is_party AS is_party
    FROM counts c
    JOIN actor_base a ON a.actor_id = c.actor_id
    WHERE a.schema IN ('Organization', 'Company', 'LegalEntity')
    ORDER BY c.connections DESC
    """
)


def _actor_schema_filter(schema: Optional[List[str]]) -> List[str]:
    if not schema:
        return sorted(ACTOR_SCHEMATA)
    filtered = [value for value in schema if value in ACTOR_SCHEMATA]
    if not filtered:
        return sorted(ACTOR_SCHEMATA)
    return sorted(set(filtered))


SCHEMA_CHILDREN: Dict[str, List[str]] = {
    "LegalEntity": ["Organization", "Person"],
    "Organization": ["Company", "PublicBody"],
}


def _expand_schema(schema_name: str, output: set[str]) -> None:
    output.add(schema_name)
    for child in SCHEMA_CHILDREN.get(schema_name, []):
        if child in ACTOR_SCHEMATA and child not in output:
            _expand_schema(child, output)


def _expand_actor_schema_filter(
    schema: Optional[List[str]],
) -> tuple[List[str], List[str]]:
    requested = _actor_schema_filter(schema)
    expanded: set[str] = set()
    for schema_name in requested:
        _expand_schema(schema_name, expanded)
    applied = sorted(expanded)
    return requested, applied


def _get_top_actor_rankings(limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    try:
        engine = get_published_engine()
        with engine.connect() as conn:
            rows = conn.execute(TOP_ACTOR_SQL).fetchall()

        lobbying: List[Dict[str, Any]] = []
        organizations: List[Dict[str, Any]] = []

        for row in rows:
            item = {
                "id": str(row._mapping["id"]),
                "name": str(row._mapping["name"]),
                "schema": str(row._mapping["schema"]),
                "connections": int(row._mapping["connections"]),
            }
            is_lobby = int(row._mapping["is_lobby"] or 0) == 1
            is_party = int(row._mapping["is_party"] or 0) == 1

            if is_lobby and len(lobbying) < limit:
                lobbying.append(item)

            if not is_lobby and not is_party and len(organizations) < limit:
                organizations.append(item)

            if len(lobbying) >= limit and len(organizations) >= limit:
                break

        lobbying.sort(key=lambda x: x["connections"], reverse=True)
        organizations.sort(key=lambda x: x["connections"], reverse=True)

        return {
            "top_lobbying_companies": lobbying,
            "top_organizations": organizations,
        }
    except Exception as exc:
        log.exception("Failed to compute top actor rankings: %s", exc)
        return {
            "top_lobbying_companies": [],
            "top_organizations": [],
        }


@lru_cache(maxsize=1)
def postgres_search_ready() -> bool:
    """Check if production search materialized view is available."""
    try:
        engine = get_published_engine()
        with engine.connect() as conn:
            relation = conn.execute(
                text("SELECT to_regclass('public.entity_search')")
            ).scalar()
            return relation is not None
    except Exception as exc:
        log.warning("Could not verify Postgres search objects: %s", exc)
        return False


def _search_response(
    results: List[Dict[str, Any]],
    total: int,
    offset: int,
    limit: int,
    requested_schema: List[str],
    applied_schema: List[str],
) -> Dict[str, Any]:
    return {
        "results": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_next": (offset + len(results)) < total,
        "schema": applied_schema,
        "requested_schema": requested_schema,
        "applied_schema": applied_schema,
    }


def _redirect_payload(ent, route: str) -> Dict[str, Any]:
    return {
        "redirect": True,
        "correct_route": route,
        **serialize_view_entity(ent),
    }


def _get_entity_or_404(id: str, detail: str):
    if not view:
        raise HTTPException(status_code=503, detail="Database not ready")

    ent = view.get_entity(id)
    if ent is None:
        raise HTTPException(status_code=404, detail=detail)
    return ent


class DedupeJudgementBody(BaseModel):
    left_id: str
    right_id: str
    judgement: str
    user_id: str
    user_name: Optional[str] = None


class DedupeLockedPairBody(BaseModel):
    left_id: str
    right_id: str


class DedupeClusterJudgementBody(BaseModel):
    entity_ids: List[str]
    selected_ids: List[str]
    locked_pairs: List[DedupeLockedPairBody]
    intent: str
    user_id: str
    user_name: Optional[str] = None


def _locked_pairs_from_body(
    pairs: List[DedupeLockedPairBody],
) -> List[LockedPair]:
    return [
        {"left_id": pair.left_id, "right_id": pair.right_id, "score": None}
        for pair in pairs
    ]


def require_admin_secret(x_admin_secret: Optional[str] = Header(default=None)) -> None:
    if x_admin_secret != get_admin_api_secret():
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/")
def root() -> Dict[str, object]:
    return {
        "name": "Muckrake API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/datasets")
def list_datasets() -> List[Dict[str, Any]]:
    """List all available datasets with metadata."""
    all_meta = get_all_datasets_metadata()
    output = []
    for name in list_all_dataset_names():
        output.append(all_meta.get(name, {"name": name, "title": name}))
    return output


@app.get("/admin/dedupe/next")
def get_admin_dedupe_candidate(
    user_id: str,
    user_name: Optional[str] = None,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    return {"candidate": get_next_dedupe_candidate(user_id, user_name=user_name)}


@app.post("/admin/dedupe/judge")
def judge_admin_dedupe_candidate(
    body: DedupeJudgementBody,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    try:
        canonical_id = record_dedupe_judgement(
            body.left_id,
            body.right_id,
            body.judgement,
            body.user_id,
            user_name=body.user_name,
        )
    except DedupeLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "canonical_id": canonical_id}


@app.get("/admin/dedupe-clusters/next")
def get_admin_dedupe_cluster(
    user_id: str,
    user_name: Optional[str] = None,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    return {"candidate": get_next_dedupe_cluster(user_id, user_name=user_name)}


@app.post("/admin/dedupe-clusters/judge")
def judge_admin_dedupe_cluster(
    body: DedupeClusterJudgementBody,
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    try:
        locked_pairs = _locked_pairs_from_body(body.locked_pairs)
        if body.intent == "skip":
            skip_dedupe_cluster(locked_pairs, body.user_id)
            canonical_id = None
        else:
            judgement = {
                "match": "positive",
                "no_match": "negative",
                "unsure": "unsure",
            }.get(body.intent)
            if judgement is None:
                raise ValueError(f"Invalid cluster intent: {body.intent}")

            canonical_id = record_dedupe_cluster_judgement(
                body.entity_ids,
                body.selected_ids,
                locked_pairs,
                judgement,
                body.user_id,
                user_name=body.user_name,
            )
    except DedupeLockError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "canonical_id": canonical_id}


@app.get("/entities")
def list_entities(
    dataset: Optional[List[str]] = Query(None),
    schema: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
) -> Dict[str, object]:
    if not view:
        return {"results": [], "total": 0}

    allowed_schemata = _schema_filter_values(schema) if schema else None
    results = []

    # Python-side filtering for simplicity in this MVP
    # Optimization: use SQL-side filtering if performance becomes an issue
    entities = view.entities()

    total = 0
    for ent in entities:
        if allowed_schemata is not None and ent.schema.name not in allowed_schemata:
            continue
        if dataset and not (set(dataset) & set(ent.datasets)):
            continue

        total += 1
        if total <= offset:
            continue
        if len(results) >= limit:
            continue
        results.append(serialize_view_entity(ent))

    return {
        "count": len(results),
        "offset": offset,
        "limit": limit,
        "total": total,
        "results": results,
    }


@app.get("/profile/{id}")
def get_profile(
    id: str,
    activity_limit: int = PROFILE_ACTIVITY_DEFAULT_LIMIT,
    activity_offset: int = 0,
) -> Dict[str, Any]:
    """Endpoint for actor profiles, includes adjacency (timeline)."""
    ent = _get_entity_or_404(id, "Profile not found")

    # If it's not actually an actor, suggest a redirect
    if not is_actor(ent.schema.name):
        return _redirect_payload(ent, f"/statement/{ent.id}")

    activity_limit, activity_offset = _normalize_profile_activity_pagination(
        activity_limit, activity_offset
    )

    data = serialize_view_entity(ent)
    try:
        data["adjacent"] = _serialize_profile_relationships(
            _load_profile_relationship_items(id)
        )
        data["activities"] = _paginate_profile_activities_sql(
            id, activity_limit, activity_offset
        )
        data["has_network"] = _has_profile_direct_adjacent(
            ent
        ) or _has_profile_inverted_adjacent(id)
    except Exception as exc:
        log.exception(
            "Profile pagination query failed, falling back to full adjacency scan: %s",
            exc,
        )
        adjacent_items = _collect_profile_adjacent(ent)
        data["adjacent"] = _serialize_profile_relationships(adjacent_items)
        data["activities"] = _paginate_profile_activities(
            adjacent_items, activity_limit, activity_offset
        )
        data["has_network"] = len(adjacent_items) > 0
    return data


@app.get("/profile/{id}/activities")
def get_profile_activities(
    id: str,
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    ent = _get_entity_or_404(id, "Profile not found")

    if not is_actor(ent.schema.name):
        raise HTTPException(status_code=404, detail="Profile not found")

    limit, offset = _normalize_profile_activity_pagination(limit, offset)
    try:
        return _paginate_profile_activities_sql(id, limit, offset)
    except Exception as exc:
        log.exception(
            "Profile activities query failed, falling back to full adjacency scan: %s",
            exc,
        )
        adjacent_items = _collect_profile_adjacent(ent)
        return _paginate_profile_activities(adjacent_items, limit, offset)


@app.get("/sitemaps/profiles")
def list_profile_sitemap_entries(
    limit: int = 50000,
    offset: int = 0,
) -> Dict[str, Any]:
    """List actor profile paths for sitemap generation."""
    limit = max(1, min(limit, 50000))
    offset = max(0, offset)

    if not view:
        return {
            "results": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "has_next": False,
        }

    if postgres_search_ready():
        try:
            engine = get_published_engine()
            with engine.connect() as conn:
                total = conn.execute(
                    ACTOR_SITEMAP_COUNT_SQL,
                    {"schemas": sorted(ACTOR_SCHEMATA)},
                ).scalar()
                rows = conn.execute(
                    ACTOR_SITEMAP_IDS_SQL,
                    {
                        "schemas": sorted(ACTOR_SCHEMATA),
                        "limit": limit,
                        "offset": offset,
                    },
                )
                results = [
                    {
                        "id": str(row._mapping["id"]),
                        "path": f"/profile/{row._mapping['id']}",
                    }
                    for row in rows
                ]
            total = int(total or 0)
            return {
                "results": results,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_next": (offset + len(results)) < total,
            }
        except Exception as exc:
            log.exception(
                "Profile sitemap query failed, falling back to Python scan: %s", exc
            )

    include_schema = []
    for schema_name in sorted(ACTOR_SCHEMATA):
        schema_obj = model.get(schema_name)
        if schema_obj is not None:
            include_schema.append(schema_obj)

    results = []
    seen_ids = set()
    total = 0
    for ent in view.entities(include_schemata=include_schema):
        if ent.id in seen_ids:
            continue

        seen_ids.add(ent.id)
        total += 1
        if total <= offset:
            continue
        if len(results) >= limit:
            continue

        results.append({"id": ent.id, "path": f"/profile/{ent.id}"})

    return {
        "results": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_next": (offset + len(results)) < total,
    }


@app.get("/statement/{id}")
def get_statement(id: str) -> Dict[str, Any]:
    """Endpoint for statements/events, simple view."""
    ent = _get_entity_or_404(id, "Statement not found")

    # If it's actually an actor, suggest a redirect to profile
    if is_actor(ent.schema.name):
        return _redirect_payload(ent, f"/profile/{ent.id}")

    return serialize_view_entity(ent)


@app.get("/search")
def search_entities(
    q: str,
    limit: int = 25,
    offset: int = 0,
    schema: Optional[List[str]] = Query(None),
) -> Dict[str, Any]:
    requested_schema, schema_filter = _expand_actor_schema_filter(schema)

    if not view:
        return _search_response([], 0, offset, limit, requested_schema, schema_filter)

    query = q.strip()
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    if not query:
        return _search_response([], 0, offset, limit, requested_schema, schema_filter)

    if postgres_search_ready():
        try:
            engine = get_published_engine()
            with engine.connect() as conn:
                total = conn.execute(
                    POSTGRES_SEARCH_COUNT_SQL,
                    {
                        "query": query,
                        "similarity": 0.25,
                        "word_similarity": 0.55,
                        "schemas": schema_filter,
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
                        "schemas": schema_filter,
                    },
                )
                results = []
                for row in rows:
                    item = dict(row._mapping)
                    item.pop("sim_display", None)
                    item.pop("sim_word", None)
                    results.append(item)
            total = int(total or 0)
            return _search_response(
                results, total, offset, limit, requested_schema, schema_filter
            )
        except Exception as exc:
            log.exception(
                "Postgres search failed, falling back to Python scan: %s", exc
            )

    matched = []
    seen_ids = set()
    query_lower = query.lower()

    include_schema = []
    for schema_name in schema_filter:
        schema_obj = model.get(schema_name)
        if schema_obj is not None:
            include_schema.append(schema_obj)

    for ent in view.entities(include_schemata=include_schema):
        if ent.id in seen_ids:
            continue
        if query_lower in ent.caption.lower():
            matched.append({"id": ent.id, "name": ent.caption, "type": ent.schema.name})
            seen_ids.add(ent.id)

    total = len(matched)
    results = matched[offset : offset + limit]

    return _search_response(
        results, total, offset, limit, requested_schema, schema_filter
    )


@app.get("/stats")
def get_stats() -> Dict[str, Any]:
    now = time.time()
    if _stats_cache["value"] is not None and _stats_cache["expires_at"] > now:
        return _stats_cache["value"]

    if not view:
        empty = {
            "organizations": 0,
            "individuals": 0,
            "public_bodies": 0,
            "datasets": 0,
            "total_actors": 0,
            "by_schema": {},
            "top_lobbying_companies": [],
            "top_organizations": [],
        }
        _stats_cache["value"] = empty
        _stats_cache["expires_at"] = now + STATS_CACHE_TTL_SECONDS
        return empty

    schema_counts: Dict[str, int] = {schema: 0 for schema in ACTOR_SCHEMATA}

    if postgres_search_ready():
        try:
            engine = get_published_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT schema, COUNT(*)::bigint AS count
                        FROM entity_search
                        WHERE schema = ANY(:schemas)
                        GROUP BY schema
                        """
                    ),
                    {"schemas": sorted(ACTOR_SCHEMATA)},
                )
                for row in rows:
                    schema_name = str(row._mapping["schema"])
                    schema_counts[schema_name] = int(row._mapping["count"])
        except Exception as exc:
            log.exception(
                "Postgres stats query failed, falling back to Python scan: %s", exc
            )

    if sum(schema_counts.values()) == 0:
        include_schema = []
        for schema_name in sorted(ACTOR_SCHEMATA):
            schema_obj = model.get(schema_name)
            if schema_obj is not None:
                include_schema.append(schema_obj)
        for ent in view.entities(include_schemata=include_schema):
            schema_name = ent.schema.name
            if schema_name in schema_counts:
                schema_counts[schema_name] += 1

    organizations = (
        schema_counts.get("Organization", 0)
        + schema_counts.get("Company", 0)
        + schema_counts.get("LegalEntity", 0)
    )
    individuals = schema_counts.get("Person", 0)
    public_bodies = schema_counts.get("PublicBody", 0)

    payload = {
        "organizations": organizations,
        "individuals": individuals,
        "public_bodies": public_bodies,
        "datasets": len(list_all_dataset_names()),
        "total_actors": organizations + individuals + public_bodies,
        "by_schema": schema_counts,
        **_get_top_actor_rankings(),
    }
    _stats_cache["value"] = payload
    _stats_cache["expires_at"] = now + STATS_CACHE_TTL_SECONDS
    return payload


@app.get("/entities/{id}/graph")
def get_entity_graph(id: str) -> Dict[str, Any]:
    """Get aggregated 1st-degree connections for graph visualization."""
    if not view:
        raise HTTPException(status_code=503, detail="Database not ready")

    return get_entity_graph_data(view, id)
