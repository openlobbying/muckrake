"""The generated reference docs match the code.

If this fails, run ``uv run python scripts/gen_docs.py`` and commit the result.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from muckrake.settings import ENV_VARS

ROOT = Path(__file__).parent.parent


def _gen_docs() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts" / "gen_docs.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_reference_is_current():
    assert (ROOT / "docs" / "cli.md").read_text() == _gen_docs().render_cli()


def test_env_reference_is_current():
    assert (ROOT / "docs" / "env.md").read_text() == _gen_docs().render_env()


def test_every_env_var_read_in_src_is_documented():
    pattern = re.compile(r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z0-9_]+)["']""")
    read = {
        name
        for path in (ROOT / "src").rglob("*.py")
        for name in pattern.findall(path.read_text(encoding="utf-8"))
    }
    assert read, "the pattern found no environment reads"
    assert read <= {var.name for var in ENV_VARS}
