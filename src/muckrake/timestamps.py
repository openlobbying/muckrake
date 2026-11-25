"""The ``first_seen`` timestamps a crawl carries over from the previous run's pack."""

from __future__ import annotations

from array import array
from collections.abc import Iterable

import numpy as np

DIGEST_HEX = 40  # Statement IDs are SHA-1 hex digests.


def _digest(stmt_id: str) -> bytes | None:
    """The 20-byte digest a lowercase SHA-1 hex ID spells, or None for any other ID."""
    if len(stmt_id) != DIGEST_HEX:
        return None
    try:
        digest = bytes.fromhex(stmt_id)
    except ValueError:
        return None
    # The round trip rejects uppercase and whitespace, so each digest stands for one ID.
    return digest if digest.hex() == stmt_id else None


class FirstSeen:
    """Statement ID -> ``first_seen``, held compactly.

    A ``dict[str, str]`` costs ~200 bytes a statement, ~2 GB for a 10M-statement
    pack. This keeps each SHA-1 ID as its 20-byte digest in one sorted array, and
    each timestamp as an index into the few distinct ones (one per past run): 24
    bytes a statement. IDs that aren't SHA-1 hex go in a plain dict. When an ID
    repeats, the last value wins, as in a dict.
    """

    def __init__(self) -> None:
        self._keys = np.empty(0, dtype=f"S{DIGEST_HEX // 2}")
        self._codes = np.empty(0, dtype=np.uint32)
        self._values: list[str] = []
        self._other: dict[str, str] = {}

    @classmethod
    def from_items(cls, items: Iterable[tuple[str, str]]) -> FirstSeen:
        """Build from (statement ID, first_seen) pairs."""
        index = cls()
        index.fill(items)
        return index

    def fill(self, items: Iterable[tuple[str, str]]) -> None:
        """Fill an empty index. If ``items`` raises, the pairs read so far are kept."""
        if len(self):
            raise ValueError("FirstSeen is filled once")
        digests = bytearray()
        codes = array("I")
        value_codes: dict[str, int] = {}
        try:
            for stmt_id, first_seen in items:
                code = value_codes.setdefault(first_seen, len(value_codes))
                digest = _digest(stmt_id)
                if digest is None:
                    self._other[stmt_id] = first_seen
                else:
                    digests += digest
                    codes.append(code)
        finally:
            self._values = list(value_codes)
            keys = np.frombuffer(digests, dtype=self._keys.dtype)
            # Stable, so among repeated IDs the last one read sorts last.
            order = np.argsort(keys, kind="stable")
            self._keys = keys[order]
            self._codes = np.frombuffer(codes, dtype=np.uint32)[order]

    def get(self, stmt_id: str, default: str) -> str:
        digest = _digest(stmt_id)
        if digest is None:
            return self._other.get(stmt_id, default)
        i = int(np.searchsorted(self._keys, digest, side="right")) - 1
        # numpy drops trailing NUL bytes from fixed-width bytes it hands back.
        if i >= 0 and self._keys[i] == digest.rstrip(b"\0"):
            return self._values[self._codes[i]]
        return default

    def __len__(self) -> int:
        """Pairs held: an ID that repeated counts once per pair, unlike a dict."""
        return len(self._keys) + len(self._other)
