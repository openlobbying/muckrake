from __future__ import annotations

import hashlib
import random
import tracemalloc
from collections.abc import Callable, Iterator

import pytest

from muckrake.timestamps import FirstSeen


def sha1(n: int) -> str:
    return hashlib.sha1(str(n).encode()).hexdigest()


def test_matches_a_dict():
    rng = random.Random(1)
    runs = [f"2026-11-{day:02d}T10:00:00.000000" for day in range(1, 11)]
    pairs = [(sha1(n), rng.choice(runs)) for n in range(5000)]
    # Repeated IDs (last one wins), IDs ending in NUL bytes, and IDs that aren't
    # lowercase SHA-1 hex.
    pairs += [(sha1(n), rng.choice(runs)) for n in range(0, 5000, 7)]
    pairs += [("00" * 20, runs[0]), ("ab" * 19 + "00", runs[1]), ("ab" * 20, runs[2])]
    pairs += [(sha1(1).upper(), runs[3]), ("custom-id", runs[4]), ("", runs[5])]
    expected = dict(pairs)
    index = FirstSeen.from_items(pairs)

    probes = list(expected) + [sha1(n) for n in range(5000, 6000)]
    probes += ["ab" * 19 + "01", "00" * 19 + "01", sha1(2).upper(), "other", " " + sha1(3)[1:]]
    for stmt_id in probes:
        assert index.get(stmt_id, "new") == expected.get(stmt_id, "new"), stmt_id


def test_empty():
    index = FirstSeen()
    assert len(index) == 0
    assert index.get(sha1(1), "new") == "new"


def test_keeps_pairs_read_before_an_error():
    def pairs() -> Iterator[tuple[str, str]]:
        yield sha1(1), "2026-01-01"
        yield "custom", "2026-01-02"
        raise ValueError("broken pack")

    index = FirstSeen()
    with pytest.raises(ValueError):
        index.fill(pairs())
    assert index.get(sha1(1), "new") == "2026-01-01"
    assert index.get("custom", "new") == "2026-01-02"


def traced_bytes(build: Callable[[], object]) -> tuple[int, int]:
    """Bytes held by what ``build`` returns, and the peak while building it."""
    tracemalloc.start()
    try:
        held = build()
        size, peak = tracemalloc.get_traced_memory()
        del held
        return size, peak
    finally:
        tracemalloc.stop()


def test_far_smaller_than_a_dict():
    n = 100_000

    def pairs() -> Iterator[tuple[str, str]]:
        # Fresh strings for every pair, as reading a pack makes them.
        for i in range(n):
            yield sha1(i), f"2026-11-{i % 3 + 1:02d}T22:37:46.763244"

    dict_size, dict_peak = traced_bytes(lambda: dict(pairs()))
    index_size, index_peak = traced_bytes(lambda: FirstSeen.from_items(pairs()))
    assert index_size / n < 30
    assert dict_size > 6 * index_size
    assert dict_peak > 2.5 * index_peak
