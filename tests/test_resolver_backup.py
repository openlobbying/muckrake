from __future__ import annotations

import json
from pathlib import Path

from nomenklatura.db import make_session
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver

from muckrake.dedupe.backup import export_judgements, import_judgements


def _resolver(uri: str):
    session_cm = make_session(uri)
    session = session_cm.__enter__()
    resolver: Resolver = Resolver(session, create=True)
    resolver.load_into_memory()
    return session_cm, resolver


def _seed(resolver: Resolver) -> None:
    resolver.decide("a1", "a2", Judgement.POSITIVE, user="warren")
    resolver.decide("b1", "b2", Judgement.NEGATIVE, user="muckrake/manual")
    resolver.decide("c1", "c2", Judgement.POSITIVE, user="muckrake/xref")
    resolver.suggest("d1", "d2", 0.9, user="muckrake/xref")


def test_export_then_import_restores_human_judgements(tmp_path: Path) -> None:
    path = tmp_path / "judgements.jsonl.gz"
    cm, resolver = _resolver(f"sqlite:///{tmp_path / 'a.db'}")
    _seed(resolver)
    # People only, as edges: a merge is an edge per entity to its canonical ID.
    assert export_judgements(resolver, path) == 3
    cm.__exit__(None, None, None)

    cm, fresh = _resolver(f"sqlite:///{tmp_path / 'b.db'}")
    assert import_judgements(fresh, path) == (3, 0)
    assert fresh.get_judgement("a1", "a2") == Judgement.POSITIVE
    assert fresh.get_judgement("b1", "b2") == Judgement.NEGATIVE
    assert fresh.get_judgement("c1", "c2") == Judgement.NO_JUDGEMENT
    assert {e.user for e in fresh.all_edges()} == {"warren", "muckrake/manual"}
    # A second import changes nothing: every pair is already judged.
    assert import_judgements(fresh, path) == (0, 3)
    cm.__exit__(None, None, None)


def test_all_includes_automatic_judgements_but_never_suggestions(tmp_path: Path) -> None:
    path = tmp_path / "all.jsonl"
    cm, resolver = _resolver(f"sqlite:///{tmp_path / 'a.db'}")
    _seed(resolver)
    assert export_judgements(resolver, path, include_automatic=True) == 5
    users = {json.loads(line)["user"] for line in path.read_text().splitlines()}
    cm.__exit__(None, None, None)
    assert users == {"warren", "muckrake/manual", "muckrake/xref"}


def test_import_never_overwrites_a_local_judgement(tmp_path: Path) -> None:
    path = tmp_path / "judgements.jsonl"
    cm, resolver = _resolver(f"sqlite:///{tmp_path / 'a.db'}")
    resolver.decide("a1", "a2", Judgement.POSITIVE, user="warren")
    resolver.decide("e1", "e2", Judgement.POSITIVE, user="warren")
    export_judgements(resolver, path)
    cm.__exit__(None, None, None)

    cm, local = _resolver(f"sqlite:///{tmp_path / 'b.db'}")
    local.decide("a1", "a2", Judgement.NEGATIVE, user="nicu")
    local.suggest("e1", "e2", 0.8, user="muckrake/xref")
    assert import_judgements(local, path) == (2, 2)
    assert local.get_judgement("a1", "a2") == Judgement.NEGATIVE  # kept apart
    assert local.get_judgement("e1", "e2") == Judgement.POSITIVE  # a suggestion is replaced
    cm.__exit__(None, None, None)


def test_a_merge_is_not_imported_across_a_local_negative_via_another_entity(tmp_path: Path) -> None:
    path = tmp_path / "judgements.jsonl"
    cm, resolver = _resolver(f"sqlite:///{tmp_path / 'a.db'}")
    resolver.decide("x1", "x2", Judgement.POSITIVE, user="warren")
    export_judgements(resolver, path)
    cm.__exit__(None, None, None)

    cm, local = _resolver(f"sqlite:///{tmp_path / 'b.db'}")
    local.decide("x2", "x3", Judgement.POSITIVE, user="nicu")
    local.decide("x1", "x3", Judgement.NEGATIVE, user="nicu")
    # Importing x1 = x2 would join x1 to x3, which is kept apart here.
    assert import_judgements(local, path) == (0, 2)
    assert local.get_judgement("x1", "x2") == Judgement.NEGATIVE
    cm.__exit__(None, None, None)
