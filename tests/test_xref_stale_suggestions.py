from __future__ import annotations

from pathlib import Path

from nomenklatura.db import make_session
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver

from muckrake.dedupe.dedupe import prune_stale_suggestions


def test_suggestions_for_gone_entities_are_removed(tmp_path: Path) -> None:
    with make_session(f"sqlite:///{tmp_path / 'r.db'}") as session:
        resolver: Resolver = Resolver(session, create=True)
        resolver.load_into_memory()
        resolver.decide("x1", "x2", Judgement.POSITIVE, user="warren")
        cluster = resolver.get_canonical("x1")
        resolver.decide("j1", "gone-1", Judgement.NEGATIVE, user="warren")
        resolver.suggest("a", "b", 0.9, user="muckrake/xref")  # both present
        resolver.suggest("a", "gone-2", 0.95, user="muckrake/xref")  # stale
        resolver.suggest(cluster, "b", 0.8, user="muckrake/xref")  # cluster present
        resolver.suggest("gone-3", "gone-4", 0.7, user="muckrake/xref")  # stale

        removed = prune_stale_suggestions(resolver, {"a", "b", "x1", "x2", "j1"})

        open_pairs = {
            frozenset((e.source.id, e.target.id))
            for e in resolver.all_edges(include_suggestions=True)
            if e.judgement == Judgement.NO_JUDGEMENT
        }
        assert removed == 2
        assert open_pairs == {frozenset(("a", "b")), frozenset((cluster, "b"))}
        # Judgements are never touched, even when an entity has gone.
        assert resolver.get_judgement("x1", "x2") == Judgement.POSITIVE
        assert resolver.get_judgement("j1", "gone-1") == Judgement.NEGATIVE
