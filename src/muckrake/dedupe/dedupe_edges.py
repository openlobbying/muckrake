import logging
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from nomenklatura.judgement import Judgement

from muckrake.dataset import find_datasets, load_config
from muckrake.dedupe.dedupe import load_statements
from muckrake.store import get_level_store, get_resolver

log = logging.getLogger(__name__)


ROLE_NORMALIZATION = {
    "consultant lobbyist": "lobbyist",
    "lobbyist": "lobbyist",
}


@dataclass(frozen=True)
class EdgeRecord:
    entity_id: str
    source: str
    target: str
    schema: str
    role: Optional[str]
    start: Optional[date]
    end: Optional[date]


def _normalize_role(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return ROLE_NORMALIZATION.get(normalized, normalized)


def _parse_date(value: Optional[str], is_end: bool = False) -> Optional[date]:
    if value is None:
        return None
    if len(value) == 7:
        year, month = value.split("-")
        day = monthrange(int(year), int(month))[1] if is_end else 1
        return date.fromisoformat(f"{value}-{day:02d}")
    return date.fromisoformat(value)


def _edge_vertices(entity) -> Optional[tuple[str, str]]:
    source_prop = entity.schema.source_prop
    target_prop = entity.schema.target_prop
    if source_prop is None or target_prop is None:
        return None

    sources = list(entity.get(source_prop))
    targets = list(entity.get(target_prop))
    if len(sources) != 1 or len(targets) != 1:
        return None

    source = str(sources[0])
    target = str(targets[0])
    if not entity.schema.edge_directed:
        source, target = sorted((source, target))
    return source, target


def _extract_edge_record(entity, resolver) -> Optional[EdgeRecord]:
    if entity.id is None or not entity.schema.edge:
        return None
    if not entity.schema.is_a("Representation"):
        return None

    vertices = _edge_vertices(entity)
    if vertices is None:
        return None

    source = resolver.get_canonical(vertices[0])
    target = resolver.get_canonical(vertices[1])

    roles = sorted(str(value) for value in entity.get("role") if value)
    role = _normalize_role(roles[0] if roles else None)

    starts = sorted(str(value) for value in entity.get("startDate") if value)
    ends = sorted(str(value) for value in entity.get("endDate") if value)

    try:
        start = _parse_date(starts[0], is_end=False) if starts else None
        end = _parse_date(ends[0], is_end=True) if ends else None
    except ValueError:
        return None

    if start is not None and end is not None and end < start:
        return None

    return EdgeRecord(
        entity_id=entity.id,
        source=source,
        target=target,
        schema=entity.schema.name,
        role=role,
        start=start,
        end=end,
    )


def _is_mergeable(a: EdgeRecord, b: EdgeRecord, max_gap_days: int) -> bool:
    if a.start is not None and b.start is not None and a.start == b.start:
        if (a.end is None) != (b.end is None):
            return True

    if a.start is None or a.end is None or b.start is None or b.end is None:
        return False

    return b.start <= a.end + timedelta(days=max_gap_days)


def _build_clusters(
    records: list[EdgeRecord], max_gap_days: int
) -> list[list[EdgeRecord]]:
    grouped: dict[tuple[str, str, str, Optional[str]], list[EdgeRecord]] = defaultdict(
        list
    )
    for record in records:
        key = (record.source, record.target, record.schema, record.role)
        grouped[key].append(record)

    clusters: list[list[EdgeRecord]] = []
    for group in grouped.values():
        group.sort(
            key=lambda rec: (
                rec.start or date.min,
                rec.end or date.max,
                rec.entity_id,
            )
        )

        chain: list[EdgeRecord] = []
        for record in group:
            if not chain:
                chain = [record]
                continue

            previous = chain[-1]
            if _is_mergeable(previous, record, max_gap_days=max_gap_days):
                chain.append(record)
            else:
                if len(chain) > 1:
                    clusters.append(chain)
                chain = [record]

        if len(chain) > 1:
            clusters.append(chain)

    return clusters


def run_dedupe_edges(
    dataset_name: Optional[str] = None,
    max_gap_days: int = 1,
    dry_run: bool = False,
) -> None:
    """Deduplicate relationship edges in resolver (zavod-style)."""
    if max_gap_days < 0:
        raise ValueError("--max-gap-days must be >= 0")

    configs = find_datasets(dataset_name)
    if not configs:
        raise ValueError(f"No datasets found matching '{dataset_name}'")

    dataset_names = [load_config(config).name for config in configs]
    store = get_level_store(dataset_names, fresh=True)
    load_statements(store, dataset_names)
    view = store.view(store.dataset)

    resolver = get_resolver()
    resolver.begin()

    try:
        records: list[EdgeRecord] = []
        for entity in view.entities():
            record = _extract_edge_record(entity, resolver)
            if record is not None:
                records.append(record)

        clusters = _build_clusters(records, max_gap_days=max_gap_days)
        if dry_run:
            merged_entities = sum(len(cluster) for cluster in clusters)
            log.info(
                "Dry-run complete: %s clusters would be merged (%s edge entities)",
                len(clusters),
                merged_entities,
            )
            resolver.rollback()
            return

        merged_entities = 0
        for cluster in clusters:
            canonical = resolver.get_canonical(cluster[0].entity_id)
            for record in cluster[1:]:
                other = resolver.get_canonical(record.entity_id)
                if other == canonical:
                    continue
                canonical = resolver.decide(
                    canonical,
                    other,
                    judgement=Judgement.POSITIVE,
                    user="muckrake/edge-dedupe",
                ).id
                merged_entities += 1

        resolver.commit()
        log.info(
            "Edge dedupe complete: merged %s clusters (%s edge entities)",
            len(clusters),
            merged_entities,
        )
    except Exception:
        resolver.rollback()
        raise
