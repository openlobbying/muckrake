from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from heapq import heappop, heappush
from typing import Any, Dict, Iterable, List, Optional, TypedDict

from nomenklatura.judgement import Judgement
from sqlalchemy import text
from sqlalchemy.engine import Connection

from muckrake.api.view import get_view, serialize_view_entity
from muckrake.db import get_resolver
from muckrake.dedupe.review import (
    DedupeLockError,
    LOCK_TTL,
    _delete_expired_locks,
    _get_lock_owner,
    _get_user_locks,
    _list_candidate_rows,
    _pair_key,
    _release_locks,
    _resolve_user_label,
    _upsert_lock,
    _utc_now,
    get_lock_engine,
)

SKIP_TTL = timedelta(hours=2)


class LockedPair(TypedDict):
    left_id: str
    right_id: str
    score: Optional[float]


class ClusterMember(TypedDict):
    entity: Dict[str, Any]
    score: Optional[float]


@dataclass(frozen=True)
class ClusterCandidate:
    member_ids: List[str]
    locked_pairs: List[LockedPair]


def _delete_expired_skips(conn: Connection, now: datetime) -> None:
    conn.execute(
        text("DELETE FROM resolver_cluster_skip WHERE expires_at <= :now"),
        {"now": now.isoformat()},
    )


def _get_skipped_pair_keys(conn: Connection, user_id: str, now: datetime) -> set[str]:
    return set(
        conn.execute(
            text(
                """
                SELECT pair_key
                FROM resolver_cluster_skip
                WHERE user_id = :user_id
                  AND expires_at > :now
                """
            ),
            {"user_id": user_id, "now": now.isoformat()},
        ).scalars()
    )


def _store_skipped_pairs(
    conn: Connection,
    *,
    locked_pairs: List[LockedPair],
    user_id: str,
    now: datetime,
) -> None:
    expires_at = (now + SKIP_TTL).isoformat()
    for pair in locked_pairs:
        conn.execute(
            text(
                """
                INSERT INTO resolver_cluster_skip(
                    pair_key, left_id, right_id, user_id, created_at, expires_at
                ) VALUES (
                    :pair_key, :left_id, :right_id, :user_id, :created_at, :expires_at
                )
                ON CONFLICT (pair_key, user_id) DO UPDATE SET
                    left_id = EXCLUDED.left_id,
                    right_id = EXCLUDED.right_id,
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at
                """
            ),
            {
                "pair_key": _pair_key(pair["left_id"], pair["right_id"]),
                "left_id": pair["left_id"],
                "right_id": pair["right_id"],
                "user_id": user_id,
                "created_at": now.isoformat(),
                "expires_at": expires_at,
            },
        )


def _build_cluster_payload(
    member_ids: List[str],
    locked_pairs: List[LockedPair],
    expires_at: str,
) -> Optional[Dict[str, Any]]:
    if len(member_ids) < 2 or len(locked_pairs) == 0:
        return None

    view = get_view()
    best_scores: Dict[str, Optional[float]] = {
        entity_id: None for entity_id in member_ids
    }
    for pair in locked_pairs:
        for entity_id in (pair["left_id"], pair["right_id"]):
            score = pair["score"]
            previous = best_scores[entity_id]
            if previous is None or (score is not None and score > previous):
                best_scores[entity_id] = score

    members: List[ClusterMember] = []
    for entity_id in member_ids:
        entity = view.get_entity(entity_id)
        if entity is None:
            return None
        members.append(
            ClusterMember(
                entity=serialize_view_entity(entity),
                score=best_scores[entity_id],
            )
        )

    return {
        "members": members,
        "locked_pairs": locked_pairs,
        "lock_expires_at": expires_at,
    }


def _build_locked_cluster_payload(
    locks: List[dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not locks:
        return None

    seed = locks[0]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for lock in locks:
        adjacency[lock["left_id"]].add(lock["right_id"])
        adjacency[lock["right_id"]].add(lock["left_id"])

    queue = deque([seed["left_id"], seed["right_id"]])
    seen: set[str] = set(queue)
    member_ids = list(queue)
    while queue:
        entity_id = queue.popleft()
        for other_id in sorted(adjacency.get(entity_id, set())):
            if other_id in seen:
                continue
            seen.add(other_id)
            member_ids.append(other_id)
            queue.append(other_id)

    locked_pairs = [
        LockedPair(left_id=lock["left_id"], right_id=lock["right_id"], score=None)
        for lock in locks
        if lock["left_id"] in seen and lock["right_id"] in seen
    ]
    expires_at = max(lock["expires_at"] for lock in locks)
    return _build_cluster_payload(member_ids, locked_pairs, expires_at)


def _build_cluster_candidate(
    seed_left_id: str,
    seed_right_id: str,
    candidates: List[tuple[str, str, Optional[float]]],
    *,
    max_members: int,
) -> Optional[ClusterCandidate]:
    pair_scores: dict[str, Optional[float]] = {}
    adjacency: dict[str, list[tuple[str, Optional[float]]]] = defaultdict(list)
    for left_id, right_id, score in candidates:
        pair_key = _pair_key(left_id, right_id)
        pair_scores[pair_key] = score
        adjacency[left_id].append((right_id, score))
        adjacency[right_id].append((left_id, score))

    if _pair_key(seed_left_id, seed_right_id) not in pair_scores:
        return None

    member_ids = [seed_left_id]
    if seed_right_id != seed_left_id:
        member_ids.append(seed_right_id)
    seen = set(member_ids)
    heap: list[tuple[float, str]] = []
    for entity_id in member_ids:
        for other_id, score in adjacency.get(entity_id, []):
            if other_id not in seen:
                heappush(heap, (-(score or 0.0), other_id))

    while heap and len(member_ids) < max_members:
        _, entity_id = heappop(heap)
        if entity_id in seen:
            continue
        seen.add(entity_id)
        member_ids.append(entity_id)
        for other_id, score in adjacency.get(entity_id, []):
            if other_id not in seen:
                heappush(heap, (-(score or 0.0), other_id))

    locked_pairs = [
        LockedPair(left_id=left_id, right_id=right_id, score=score)
        for left_id, right_id, score in candidates
        if left_id in seen and right_id in seen
    ]
    if not locked_pairs:
        return None
    return ClusterCandidate(member_ids=member_ids, locked_pairs=locked_pairs)


def _claim_cluster_locks(
    conn: Connection,
    *,
    locked_pairs: List[LockedPair],
    user_id: str,
    user_name: Optional[str],
    now: datetime,
) -> bool:
    claimed_keys: List[str] = []
    for pair in locked_pairs:
        claimed = _upsert_lock(
            conn,
            left_id=pair["left_id"],
            right_id=pair["right_id"],
            user_id=user_id,
            user_name=user_name,
            now=now,
        )
        if not claimed:
            _release_locks(conn, claimed_keys)
            return False
        claimed_keys.append(_pair_key(pair["left_id"], pair["right_id"]))
    return True


def get_next_dedupe_cluster(
    user_id: str,
    user_name: Optional[str] = None,
    limit: int = 200,
    max_members: int = 8,
) -> Optional[Dict[str, Any]]:
    engine = get_lock_engine()
    now = _utc_now()

    with engine.begin() as conn:
        _delete_expired_locks(conn, now)
        _delete_expired_skips(conn, now)
        current_locks = _get_user_locks(conn, user_id, now)
        if current_locks:
            payload = _build_locked_cluster_payload(current_locks)
            if payload is not None:
                return payload
            _release_locks(conn, [lock["pair_key"] for lock in current_locks])

    with engine.begin() as conn:
        _delete_expired_skips(conn, now)
        skipped_pair_keys = _get_skipped_pair_keys(conn, user_id, now)

    candidates = [
        row
        for row in _list_candidate_rows(limit)
        if _pair_key(row[0], row[1]) not in skipped_pair_keys
    ]

    for left_id, right_id, _ in candidates:
        cluster = _build_cluster_candidate(
            left_id,
            right_id,
            candidates,
            max_members=max_members,
        )
        if cluster is None:
            continue

        with engine.begin() as conn:
            _delete_expired_locks(conn, now)
            _delete_expired_skips(conn, now)
            claimed = _claim_cluster_locks(
                conn,
                locked_pairs=cluster.locked_pairs,
                user_id=user_id,
                user_name=user_name,
                now=now,
            )
        if not claimed:
            continue

        payload = _build_cluster_payload(
            cluster.member_ids,
            cluster.locked_pairs,
            (now + LOCK_TTL).isoformat(),
        )
        if payload is not None:
            return payload

        with engine.begin() as conn:
            _release_locks(
                conn,
                [
                    _pair_key(pair["left_id"], pair["right_id"])
                    for pair in cluster.locked_pairs
                ],
            )

    return None


def record_dedupe_cluster_merge(
    entity_ids: List[str],
    selected_ids: List[str],
    locked_pairs: List[LockedPair],
    user_id: str,
    user_name: Optional[str] = None,
) -> Optional[str]:
    entity_order = list(dict.fromkeys(entity_ids))
    entity_set = set(entity_order)
    selected_order = [
        entity_id
        for entity_id in dict.fromkeys(selected_ids)
        if entity_id in entity_set
    ]
    selected_set = set(selected_order)
    unselected_order = [
        entity_id for entity_id in entity_order if entity_id not in selected_set
    ]
    if len(entity_order) < 2:
        raise ValueError("Need at least two entities in a cluster.")
    if not locked_pairs:
        raise ValueError("Missing locked pairs for this cluster.")

    engine = get_lock_engine()
    now = _utc_now()
    resolver = get_resolver()
    resolver.begin()
    try:
        with engine.begin() as conn:
            _delete_expired_locks(conn, now)
            _delete_expired_skips(conn, now)
            for pair in locked_pairs:
                pair_key = _pair_key(pair["left_id"], pair["right_id"])
                if _get_lock_owner(conn, pair_key, now) != user_id:
                    raise DedupeLockError(
                        "This cluster is not currently locked to you."
                    )

        canonical_id: Optional[str] = None
        if len(selected_order) >= 2:
            canonical_id = resolver.get_canonical(selected_order[0])
            for other_id in selected_order[1:]:
                if resolver.get_canonical(other_id) == canonical_id:
                    continue
                canonical_id = str(
                    resolver.decide(
                        canonical_id,
                        other_id,
                        Judgement.POSITIVE,
                        user=_resolve_user_label(user_id, user_name),
                    )
                )

            # Treat unchecked records as explicit non-matches against the merged group.
            for other_id in unselected_order:
                if resolver.get_canonical(other_id) == canonical_id:
                    continue
                resolver.decide(
                    canonical_id,
                    other_id,
                    Judgement.NEGATIVE,
                    user=_resolve_user_label(user_id, user_name),
                )

        resolver.commit()

        with engine.begin() as conn:
            if len(selected_order) < 2:
                _store_skipped_pairs(
                    conn,
                    locked_pairs=locked_pairs,
                    user_id=user_id,
                    now=now,
                )
            _release_locks(
                conn,
                [_pair_key(pair["left_id"], pair["right_id"]) for pair in locked_pairs],
            )

        return canonical_id
    except Exception:
        resolver.rollback()
        raise
