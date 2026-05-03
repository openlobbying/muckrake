import json
import sys
from pathlib import Path


def load_manifest(path: Path) -> dict[tuple[str, str], dict]:
    records = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") != "sheet":
                continue
            key = (record.get("url"), record.get("sheet_name"))
            records[key] = record
    return records


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: uv run python -m datasets.gb.gov_transparency.trace_diff <old.jsonl> <new.jsonl>")
        return 1

    old_records = load_manifest(Path(argv[1]))
    new_records = load_manifest(Path(argv[2]))

    old_keys = set(old_records)
    new_keys = set(new_records)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = []
    for key in sorted(old_keys & new_keys):
        old_record = old_records[key]
        new_record = new_records[key]
        old_counts = old_record.get("row_counts", {})
        new_counts = new_record.get("row_counts", {})
        if old_record.get("fingerprint") != new_record.get("fingerprint") or old_counts != new_counts:
            changed.append(
                {
                    "key": key,
                    "old_fingerprint": old_record.get("fingerprint"),
                    "new_fingerprint": new_record.get("fingerprint"),
                    "old_counts": old_counts,
                    "new_counts": new_counts,
                }
            )

    print(json.dumps({"added": added, "removed": removed, "changed": changed}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
