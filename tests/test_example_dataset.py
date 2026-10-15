"""The README quickstart's example dataset crawls, loads and is searchable."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from muckrake.cli import cli
from muckrake.entity_query import clear_query_caches

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_example_dataset_crawls_loads_and_searches(monkeypatch):
    monkeypatch.setenv("MUCKRAKE_DATASET_PATHS", str(EXAMPLES))
    clear_query_caches()
    runner = CliRunner()

    for args in (["crawl", "hello"], ["load", "hello"]):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["search", "acme"])
    assert result.exit_code == 0, result.output
    names = {item["name"] for item in json.loads(result.output)["results"]}
    assert names == {"Acme Widgets Ltd", "Acme Holdings Ltd"}
