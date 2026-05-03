from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from datasets.gb.gov_transparency.fingerprint import detect_header_row, fingerprint, header_signature
from datasets.gb.gov_transparency.normalise import normalise
from datasets.gb.gov_transparency.schema import load_schema


ROOT = Path("data/datasets/gb_gov_transparency/resources")
OUT = Path("datasets/gb/gov_transparency/baseline/current_coverage_report.json")


def main() -> None:
    matched = 0
    unknown = Counter()
    matched_fps = Counter()
    samples = defaultdict(list)
    total_sheets = 0
    total_files = 0
    parse_errors: list[dict[str, str]] = []

    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        total_files += 1
        try:
            sheets = normalise(path.read_bytes(), path.name)
        except Exception as exc:
            if len(parse_errors) < 200:
                parse_errors.append({"resource": str(path), "error": str(exc)})
            continue
        for sheet in sheets:
            total_sheets += 1
            fp = fingerprint(sheet)
            schema = load_schema(fp)
            if schema is None:
                unknown[fp] += 1
                if len(samples[fp]) < 5:
                    idx = detect_header_row(sheet)
                    samples[fp].append(
                        {
                            "resource": str(path),
                            "sheet": sheet.name,
                            "header_row_index": idx,
                            "header": sheet.rows[idx] if sheet.rows else [],
                            "signature": header_signature(sheet),
                            "preview": sheet.rows[idx : idx + 4],
                        }
                    )
            else:
                matched += 1
                matched_fps[fp] += 1

    report = {
        "total_files": total_files,
        "total_sheets": total_sheets,
        "matched_sheets": matched,
        "unknown_sheets": sum(unknown.values()),
        "matched_fingerprints": len(matched_fps),
        "unknown_fingerprints": len(unknown),
        "unknown_counts": unknown.most_common(),
        "samples": {fp: rows for fp, rows in samples.items()},
        "parse_errors": parse_errors,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "total_files": total_files,
                "total_sheets": total_sheets,
                "matched_sheets": matched,
                "unknown_sheets": sum(unknown.values()),
                "matched_fingerprints": len(matched_fps),
                "unknown_fingerprints": len(unknown),
                "top_unknown": unknown.most_common(20),
            },
            indent=2,
        )
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
