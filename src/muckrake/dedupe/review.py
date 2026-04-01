from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, TypedDict

from followthemoney import model
from nomenklatura.judgement import Judgement
from sqlalchemy import text
from sqlalchemy.engine import Connection

from muckrake.api.view import get_view, serialize_view_entity
from muckrake.db import ensure_resolver_lock_schema
from muckrake.store import get_resolver

LOCK_TTL = timedelta(minutes=30)


class DedupeLockError(ValueError):
    pass


class ResolverLock(TypedDict):
    pair_key: str
    left_id: str
    right_id: str
    user_id: str
    user_name: Optional[str]
    locked_at: str
    expires_at: str


@lru_cache(maxsize=1)
def get_lock_engine():
    return ensure_resolver_lock_schema()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _pair_key(left_id: str, right_id: str) -> str:
    left, right = sorted((left_id, right_id))
    return f"{left}::{right}"


def _resolve_user_label(user_id: str, user_name: Optional[str]) -> str:
    name = (user_name or "").strip()
    if name:
        return f"openlobbying:{user_id}:{name}"
    return f"openlobbying:{user_id}"


def _delete_expired_locks(conn: Connection, now: datetime) -> None:
    conn.execute(
        text("DELETE FROM resolver_lock WHERE expires_at <= :now"),
        {"now": now.isoformat()},
    )


def _get_user_lock(
    conn: Connection, user_id: str, now: datetime
) -> Optional[ResolverLock]:
    row = (
        conn.execute(
            text(
                """
            SELECT pair_key, left_id, right_id, user_id, user_name, locked_at, expires_at
            FROM resolver_lock
            WHERE user_id = :user_id
              AND expires_at > :now
            ORDER BY updated_at DESC
            LIMIT 1
            """
            ),
            {"user_id": user_id, "now": now.isoformat()},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return ResolverLock(**dict(row))


def _release_lock(conn: Connection, pair_key: str) -> None:
    conn.execute(
        text("DELETE FROM resolver_lock WHERE pair_key = :pair_key"),
        {"pair_key": pair_key},
    )


def _get_lock_owner(conn: Connection, pair_key: str, now: datetime) -> Optional[str]:
    return conn.execute(
        text(
            """
            SELECT user_id
            FROM resolver_lock
            WHERE pair_key = :pair_key
              AND expires_at > :now
            """
        ),
        {"pair_key": pair_key, "now": now.isoformat()},
    ).scalar_one_or_none()


def _upsert_lock(
    conn: Connection,
    *,
    left_id: str,
    right_id: str,
    user_id: str,
    user_name: Optional[str],
    now: datetime,
) -> bool:
    pair_key = _pair_key(left_id, right_id)
    expires_at = (now + LOCK_TTL).isoformat()
    result = conn.execute(
        text(
            """
            INSERT INTO resolver_lock(
                pair_key, left_id, right_id, user_id, user_name, locked_at, expires_at, updated_at
            ) VALUES (
                :pair_key, :left_id, :right_id, :user_id, :user_name, :locked_at, :expires_at, :updated_at
            )
            ON CONFLICT (pair_key) DO UPDATE SET
                left_id = EXCLUDED.left_id,
                right_id = EXCLUDED.right_id,
                user_id = EXCLUDED.user_id,
                user_name = EXCLUDED.user_name,
                locked_at = EXCLUDED.locked_at,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            WHERE resolver_lock.expires_at <= :now
               OR resolver_lock.user_id = EXCLUDED.user_id
            """
        ),
        {
            "pair_key": pair_key,
            "left_id": left_id,
            "right_id": right_id,
            "user_id": user_id,
            "user_name": user_name,
            "locked_at": now.isoformat(),
            "expires_at": expires_at,
            "updated_at": now.isoformat(),
            "now": now.isoformat(),
        },
    )
    return result.rowcount > 0


def _load_candidate_payload(
    left_id: str,
    right_id: str,
    score: Optional[float],
    expires_at: Optional[str] = None,
    verify_candidate: bool = True,
) -> Optional[Dict[str, Any]]:
    view = get_view()
    if verify_candidate:
        resolver = get_resolver(begin=True)
        try:
            if not resolver.check_candidate(left_id, right_id):
                return None
        finally:
            resolver.rollback()

    left = view.get_entity(left_id)
    right = view.get_entity(right_id)
    if left is None or right is None:
        return None

    left_schema = model.get(left.schema.name)
    right_schema = model.get(right.schema.name)
    route = (
        "profile"
        if (
            left_schema is not None
            and right_schema is not None
            and left_schema.is_a("LegalEntity")
            and right_schema.is_a("LegalEntity")
        )
        else "entity"
    )

    payload: Dict[str, Any] = {
        "left": serialize_view_entity(left),
        "right": serialize_view_entity(right),
        "score": score,
        "route": route,
    }
    if expires_at is not None:
        payload["lock_expires_at"] = expires_at
    return payload


def _list_candidate_rows(limit: int) -> List[tuple[str, str, Optional[float]]]:
    resolver = get_resolver(begin=True)
    try:
        return list(resolver.get_candidates(limit=limit))
    finally:
        resolver.rollback()


def get_next_dedupe_candidate(
    user_id: str,
    user_name: Optional[str] = None,
    limit: int = 200,
) -> Optional[Dict[str, Any]]:
    engine = get_lock_engine()
    now = _utc_now()

    with engine.begin() as conn:
        _delete_expired_locks(conn, now)

        current_lock = _get_user_lock(conn, user_id, now)
        if current_lock is not None:
            payload = _load_candidate_payload(
                current_lock["left_id"],
                current_lock["right_id"],
                score=None,
                expires_at=current_lock["expires_at"],
            )
            if payload is not None:
                return payload

            _release_lock(conn, current_lock["pair_key"])

    candidates = _list_candidate_rows(limit)

    for left_id, right_id, score in candidates:
        with engine.begin() as conn:
            claimed = _upsert_lock(
                conn,
                left_id=left_id,
                right_id=right_id,
                user_id=user_id,
                user_name=user_name,
                now=now,
            )
        if not claimed:
            continue

        payload = _load_candidate_payload(
            left_id,
            right_id,
            score=score,
            expires_at=(now + LOCK_TTL).isoformat(),
            verify_candidate=False,
        )
        if payload is not None:
            return payload

        with engine.begin() as conn:
            _release_lock(conn, _pair_key(left_id, right_id))

    return None


def record_dedupe_judgement(
    left_id: str,
    right_id: str,
    judgement_value: str,
    user_id: str,
    user_name: Optional[str] = None,
) -> str:
    try:
        judgement = Judgement(judgement_value)
    except ValueError as exc:
        raise ValueError(f"Invalid judgement: {judgement_value}") from exc

    engine = get_lock_engine()
    now = _utc_now()
    pair_key = _pair_key(left_id, right_id)
    resolver = get_resolver()
    resolver.begin()
    try:
        with engine.begin() as conn:
            _delete_expired_locks(conn, now)
            lock = _get_lock_owner(conn, pair_key, now)
            if lock != user_id:
                raise DedupeLockError("This candidate is not currently locked to you.")

        if not resolver.check_candidate(left_id, right_id):
            raise ValueError("This candidate has already been judged.")

        canonical = resolver.decide(
            left_id,
            right_id,
            judgement,
            user=_resolve_user_label(user_id, user_name),
        )
        resolver.commit()

        with engine.begin() as conn:
            _release_lock(conn, pair_key)

        return str(canonical)
    except Exception:
        resolver.rollback()
        raise
