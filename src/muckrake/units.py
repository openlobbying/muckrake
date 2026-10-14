"""Units of crawl work: independently retryable pieces of a crawl.

A crawler wraps each piece of work (a file, a page, a record) in
``Dataset.run_unit``. A unit's statements reach the run's pack only if the unit
completes; a unit that raises is recorded as failed and the crawl carries on, so
nothing from it is emitted. Each run keeps a ``units.jsonl`` ledger next to its
pack recording the byte range every succeeded unit occupies in the pack, which
lets ``crawl --retry-failed`` copy those units into a new run and re-run only the
rest.

A crawler records known gaps in its output (a pagination cap hit, a resource that
has gone missing) with ``Dataset.warn_incomplete``. Warnings raised inside a unit
are kept on its ledger record, so they survive being carried over by a retry.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from followthemoney.statement.serialize import PackStatementWriter


@dataclass
class UnitRecord:
    key: str
    status: str  # "succeeded" or "failed"
    start: int = 0
    end: int = 0
    error: str | None = None
    carried: bool = False
    warnings: list[dict[str, Any]] = field(default_factory=list)


def error_group(error: str) -> str:
    """Group key for an error message: the exception type plus its first clause."""
    return ":".join(error.split(":")[:2]).strip()[:120]


def read_ledger(path: Path) -> list[UnitRecord]:
    with path.open("r", encoding="utf-8") as fh:
        return [UnitRecord(**json.loads(line)) for line in fh if line.strip()]


class UnitLedger:
    """Records the units of one crawl run, appending each to ``path`` as it finishes.

    With ``path`` unset (e.g. a crawl streamed to stdout) units are still tracked
    in memory for the run summary, but no byte ranges are recorded.
    """

    def __init__(self, path: Path | None, writer: PackStatementWriter | None = None):
        self.path = path
        self.writer = writer
        self.records: list[UnitRecord] = []
        self.carried: set[str] = set()
        # Completeness warnings raised outside any unit.
        self.warnings: list[dict[str, Any]] = []
        self._fh = path.open("a", encoding="utf-8") if path is not None else None

    def position(self) -> int:
        """Flush the pack writer and return the byte offset of the next statement."""
        if self._fh is None or self.writer is None:
            return 0
        self.writer.flush()
        self.writer.fh.flush()
        return self.writer.fh.buffer.tell()

    def add(self, record: UnitRecord) -> None:
        self.records.append(record)
        if self._fh is not None:
            self._fh.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            self._fh.flush()

    def carry_over(self, pack_path: Path, records: list[UnitRecord]) -> None:
        """Copy every unit that fully succeeded in a previous run into this run's pack.

        A key that failed even once is left to re-run in full.
        """
        assert self.writer is not None, "carrying units over needs a pack writer"
        failed = {record.key for record in records if record.status == "failed"}
        keep = [r for r in records if r.status == "succeeded" and r.key not in failed]
        with pack_path.open("rb") as source:
            for record in sorted(keep, key=lambda r: r.start):
                source.seek(record.start)
                data = source.read(record.end - record.start)
                start = self.position()
                self.writer.fh.buffer.write(data)
                end = start + len(data)
                self.add(
                    UnitRecord(
                        record.key, "succeeded", start, end, carried=True, warnings=record.warnings
                    )
                )
                self.carried.add(record.key)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()

    def all_warnings(self) -> list[dict[str, Any]]:
        unit_warnings = [w for r in self.records for w in r.warnings]
        return self.warnings + unit_warnings

    def summary(self) -> dict[str, Any]:
        failed = [r for r in self.records if r.status == "failed"]
        groups = Counter(error_group(r.error or "") for r in failed)
        warnings = Counter(w["reason"] for w in self.all_warnings())
        return {
            "succeeded": sum(1 for r in self.records if r.status == "succeeded" and not r.carried),
            "carried": sum(1 for r in self.records if r.carried),
            "failed": len(failed),
            "failures_by_error": dict(groups.most_common()),
            "warnings": sum(warnings.values()),
            "warnings_by_reason": dict(warnings.most_common()),
        }

    @property
    def incomplete(self) -> bool:
        """Whether the run is missing data: a unit failed or a gap was recorded."""
        return any(r.status == "failed" for r in self.records) or bool(self.all_warnings())
