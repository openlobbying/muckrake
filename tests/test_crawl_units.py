from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from followthemoney.statement.serialize import read_pack_statements

from muckrake.crawl import run_crawl
from muckrake.dataset import get_dataset_path
from muckrake.runs import get_dataset_run, get_latest_crawl_run, get_latest_successful_run
from muckrake.units import error_group

# A crawler driven by plan.json: one unit per key, each emitting a Company named
# after its key. Keys in "fail" raise after emitting (so a failed unit's partial
# output must be discarded); reaching "crash_at" raises outside any unit. Every
# executed unit is appended to calls.txt.
CRAWLER = """
import json
from pathlib import Path

HERE = Path(__file__).parent


def run(dataset, key, plan):
    with (HERE / "calls.txt").open("a") as fh:
        fh.write(key + "\\n")
    entity = dataset.make("Company")
    entity.id = dataset.make_id(key)
    entity.add("name", key)
    dataset.emit(entity)
    if key in plan.get("fail", []):
        raise ValueError(f"bad unit: {key}")


def crawl(dataset):
    plan = json.loads((HERE / "plan.json").read_text())
    for key in plan["units"]:
        if key == plan.get("crash_at"):
            raise RuntimeError(f"crashed at {key}")
        dataset.run_unit(key, run, dataset, key, plan)
"""


class UnitDataset:
    def __init__(self, root: Path):
        self.name = f"units_{uuid.uuid4().hex[:8]}"
        self.dir = root / self.name
        self.dir.mkdir(parents=True)
        self.config = self.dir / "config.yml"
        self.config.write_text(yaml.safe_dump({"name": self.name, "title": self.name}))
        (self.dir / "crawler.py").write_text(CRAWLER)

    def plan(
        self, units: list[str], fail: tuple[str, ...] = (), crash_at: str | None = None
    ) -> None:
        payload = {"units": units, "fail": list(fail), "crash_at": crash_at}
        (self.dir / "plan.json").write_text(json.dumps(payload))
        (self.dir / "calls.txt").write_text("")

    def calls(self) -> list[str]:
        return (self.dir / "calls.txt").read_text().split()

    def names(self) -> list[str]:
        pack = get_dataset_path(self.name) / "statements.pack.csv"
        with pack.open("rb") as fh:
            return sorted(s.value for s in read_pack_statements(fh) if s.prop == "name")


@pytest.fixture
def unit_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], UnitDataset]:
    root = tmp_path / "datasets"
    monkeypatch.setenv("MUCKRAKE_DATASET_PATHS", str(root))
    return lambda: UnitDataset(root)


def test_all_units_succeed(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a", "b", "c"])
    run_crawl(ds.config)

    run = get_latest_crawl_run(ds.name)
    assert run is not None and run.status == "succeeded"
    assert json.loads(run.stats_json)["units"] == {
        "succeeded": 3,
        "carried": 0,
        "failed": 0,
        "failures_by_error": {},
    }
    assert ds.names() == ["a", "b", "c"]


def test_failed_unit_is_skipped_and_run_is_partial(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a", "b", "c"], fail=("b",))
    run_crawl(ds.config)

    run = get_latest_crawl_run(ds.name)
    assert run is not None and run.status == "partial"
    units = json.loads(run.stats_json)["units"]
    assert units["failed"] == 1
    assert units["failures_by_error"] == {"ValueError: bad unit": 1}
    # Nothing the failed unit emitted before raising reaches the pack.
    assert ds.names() == ["a", "c"]
    # A partial run is usable downstream (load, release-build).
    assert get_latest_successful_run(ds.name).id == run.id


def test_retry_failed_reruns_only_failed_units(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a", "b", "c"], fail=("b",))
    run_crawl(ds.config)

    ds.plan(["a", "b", "c"])
    run_crawl(ds.config, retry_failed=True)

    assert ds.calls() == ["b"]
    run = get_latest_crawl_run(ds.name)
    assert run.status == "succeeded"
    units = json.loads(run.stats_json)["units"]
    assert (units["succeeded"], units["carried"], units["failed"]) == (1, 2, 0)
    assert ds.names() == ["a", "b", "c"]


def test_crash_keeps_completed_units_for_retry(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a", "b", "c", "d"], crash_at="c")
    with pytest.raises(RuntimeError, match="crashed at c"):
        run_crawl(ds.config)

    crashed = get_latest_crawl_run(ds.name)
    assert crashed.status == "failed"
    assert json.loads(crashed.stats_json)["units"]["succeeded"] == 2

    ds.plan(["a", "b", "c", "d"])
    run_crawl(ds.config, retry_failed=True)

    assert ds.calls() == ["c", "d"]
    assert get_dataset_run(crashed.id).status == "failed"
    assert get_latest_crawl_run(ds.name).status == "succeeded"
    assert ds.names() == ["a", "b", "c", "d"]


def test_retry_chains_across_runs(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a", "b", "c"], fail=("b", "c"))
    run_crawl(ds.config)

    ds.plan(["a", "b", "c"], fail=("c",))
    run_crawl(ds.config, retry_failed=True)
    assert ds.calls() == ["b", "c"]

    ds.plan(["a", "b", "c"])
    run_crawl(ds.config, retry_failed=True)
    assert ds.calls() == ["c"]
    assert ds.names() == ["a", "b", "c"]


def test_retry_without_previous_crawl_raises(unit_dataset):
    ds = unit_dataset()
    ds.plan(["a"])
    with pytest.raises(ValueError, match="No previous crawl"):
        run_crawl(ds.config, retry_failed=True)


def test_error_group_keeps_type_and_first_clause():
    assert (
        error_group("ValueError: UNKNOWN FINGERPRINT: abc123") == "ValueError: UNKNOWN FINGERPRINT"
    )
    assert error_group("KeyError: 'name'") == "KeyError: 'name'"
