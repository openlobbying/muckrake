from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

try:
    from ..common import load_sibling_module
    from .runner import iter_crawl_order_sheets, make_context
    from ..schema import load_schema
except ImportError:
    common_spec = importlib.util.spec_from_file_location(
        f"{__name__}.common",
        Path(__file__).resolve().parents[1] / "common.py",
    )
    if common_spec is None or common_spec.loader is None:
        raise RuntimeError("Could not load gov-transparency common module")
    common_module = importlib.util.module_from_spec(common_spec)
    sys.modules[common_spec.name] = common_module
    common_spec.loader.exec_module(common_module)
    load_sibling_module = common_module.load_sibling_module
    runner_module = load_sibling_module(Path(__file__).with_name("runner.py"), __name__, "runner")
    iter_crawl_order_sheets = runner_module.iter_crawl_order_sheets
    make_context = runner_module.make_context
    load_schema = load_sibling_module(Path(__file__).resolve().parents[1] / "schema.py", __name__, "schema").load_schema


def main() -> int:
    for _dataset, provenance, source_reference, sheet, sheet_fingerprint in iter_crawl_order_sheets(skip_processed=True):
        if load_schema(sheet_fingerprint) is not None:
            continue
        print(json.dumps(make_context(provenance, source_reference, sheet, sheet_fingerprint), indent=2, ensure_ascii=False))
        return 0
    print("NO_UNKNOWN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
