import json
from pathlib import Path


class TraceWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, record: dict) -> None:
        json.dump(record, self._fh, sort_keys=True)
        self._fh.write("\n")

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()


class NullTraceWriter:
    def write(self, record: dict) -> None:
        return

    def close(self) -> None:
        return
