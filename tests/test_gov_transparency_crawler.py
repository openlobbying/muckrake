from pathlib import Path
import importlib.util
import sys
from datetime import date
import hashlib
import json
import logging
from io import StringIO
import tempfile

from org_id import make_hashed_id


MODULE_PATH = Path("datasets/gb/gov_transparency/crawler.py")
SPEC = importlib.util.spec_from_file_location(
    "muckrake.crawler.gb.gov_transparency.crawler",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
MODULE.__package__ = "muckrake.crawler.gb.gov_transparency"
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NEXT_UNKNOWN_PATH = Path("datasets/gb/gov_transparency/tools/next_unknown.py")
NEXT_UNKNOWN_SPEC = importlib.util.spec_from_file_location(
    "muckrake.crawler.gb.gov_transparency.tools.next_unknown",
    NEXT_UNKNOWN_PATH,
)
assert NEXT_UNKNOWN_SPEC is not None
assert NEXT_UNKNOWN_SPEC.loader is not None
NEXT_UNKNOWN_MODULE = importlib.util.module_from_spec(NEXT_UNKNOWN_SPEC)
NEXT_UNKNOWN_MODULE.__package__ = "muckrake.crawler.gb.gov_transparency.tools"
sys.modules[NEXT_UNKNOWN_SPEC.name] = NEXT_UNKNOWN_MODULE
NEXT_UNKNOWN_SPEC.loader.exec_module(NEXT_UNKNOWN_MODULE)

NEXT_BLOCKER_PATH = Path("datasets/gb/gov_transparency/tools/next_blocker.py")
NEXT_BLOCKER_SPEC = importlib.util.spec_from_file_location(
    "muckrake.crawler.gb.gov_transparency.tools.next_blocker",
    NEXT_BLOCKER_PATH,
)
assert NEXT_BLOCKER_SPEC is not None
assert NEXT_BLOCKER_SPEC.loader is not None
NEXT_BLOCKER_MODULE = importlib.util.module_from_spec(NEXT_BLOCKER_SPEC)
NEXT_BLOCKER_MODULE.__package__ = "muckrake.crawler.gb.gov_transparency.tools"
sys.modules[NEXT_BLOCKER_SPEC.name] = NEXT_BLOCKER_MODULE
NEXT_BLOCKER_SPEC.loader.exec_module(NEXT_BLOCKER_MODULE)

parse_period = MODULE.parse_period


class DummyDataset:
    def __init__(self, tmp_path):
        self._data = {"collections": ["example-collection"], "fail_on_unknown": False}
        self.prefix = "gb-gov"
        self.emitted = []
        self.data_path = tmp_path
        self.resources_path = tmp_path / "resources"
        self.resources_path.mkdir(parents=True, exist_ok=True)
        self.output = StringIO()
        self.log = logging.getLogger(f"gov_transparency_test_{id(self)}")
        self.log.handlers = []
        self.log.setLevel(logging.INFO)
        handler = logging.StreamHandler(self.output)
        self.log.addHandler(handler)
        self.responses = {}

    def fetch_json(self, url: str, cache_days: int = 7):
        return self.responses[url]

    def fetch_resource(self, name: str, url: str):
        payload = self.responses[url]
        path = self.resources_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def fetch_text(self, url: str, cache_days: int = 30):
        value = self.responses[url]
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def make(self, schema: str):
        from followthemoney.statement.entity import StatementEntity
        from followthemoney import Dataset as FTMDataset

        if not hasattr(self, "ftm"):
            self.ftm = FTMDataset.make({"name": "gb_gov_transparency", "prefix": self.prefix})
        return StatementEntity(self.ftm, {"schema": schema})

    def make_id(self, *parts, **kwargs):
        return make_hashed_id(self.prefix, *parts)

    def emit(self, entity):
        self.emitted.append(entity)


def test_parse_period_parses_common_quarter_title():
    start, end = parse_period("DfT: ministerial gifts, hospitality, travel and meetings, January to March 2024")

    assert start == date(2024, 1, 1)
    assert end == date(2024, 3, 31)


def test_parse_period_parses_cross_year_range():
    start, end = parse_period("Cabinet Office: ministerial meetings, October to March 2024")

    assert start == date(2023, 10, 1)
    assert end == date(2024, 3, 31)


def test_parse_period_returns_none_for_unparseable_title():
    assert parse_period("Cabinet Office transparency release") == (None, None)


def test_make_content_api_url_keeps_absolute_base_paths():
    assert MODULE.make_content_api_url("/government/publications/example-publication") == (
        "https://www.gov.uk/api/content/government/publications/example-publication"
    )


def test_crawl_emits_entities_for_known_schema(tmp_path):
    dataset = DummyDataset(tmp_path)
    dataset._data["trace_enabled"] = True
    original_load_schema = MODULE.load_schema
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_url = MODULE.make_content_api_url("/government/publications/example-publication")
    attachment_url = "https://assets.publishing.service.gov.uk/example.csv"
    dataset.responses = {
        collection_url: {"links": {"documents": [{"base_path": "/government/publications/example-publication"}]}},
        publication_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {
                "attachments": [
                    {
                        "url": attachment_url,
                        "title": "Meetings",
                        "filename": "example.csv",
                    }
                ]
            },
        },
        attachment_url: b"Minister,Date,Name of organisation or individual,Purpose of meeting\nJane Doe,2024-01-10,Example Org,Policy discussion\n",
    }

    MODULE.load_schema = lambda fingerprint: MODULE.schema_module.schema_from_dict(
        {
            "fingerprint": fingerprint,
            "sheet_type": "data",
            "activity_type": "meetings",
            "subject": {"source": "column"},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [{"type": "strptime", "format": "%Y-%m-%d", "precision": "day"}],
            },
            "mapping": {
                "official_name": 0,
                "counterparty_name": 2,
                "summary": 3,
            },
        }
        )
    try:
        MODULE.crawl(dataset)
    finally:
        MODULE.load_schema = original_load_schema

    assert any(entity.schema.name == "Meeting" for entity in dataset.emitted)
    assert any(entity.schema.name == "Person" for entity in dataset.emitted)
    assert any(entity.schema.name == "PublicBody" for entity in dataset.emitted)
    assert any(entity.schema.name == "Employment" for entity in dataset.emitted)
    assert (tmp_path / "trace" / "manifest.jsonl").exists()


def test_crawl_reports_unknown_fingerprint(tmp_path):
    dataset = DummyDataset(tmp_path)
    dataset._data["trace_enabled"] = True
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_url = MODULE.make_content_api_url("/government/publications/example-publication")
    attachment_url = "https://assets.publishing.service.gov.uk/example.csv"
    dataset.responses = {
        collection_url: {"links": {"documents": [{"base_path": "/government/publications/example-publication"}]}},
        publication_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {
                "attachments": [
                    {
                        "url": attachment_url,
                        "title": "Unknown sheet",
                        "filename": "unknown.csv",
                    }
                ]
            },
        },
        attachment_url: b"Alpha,Beta,Gamma\n1,2,3\n",
    }

    MODULE.crawl(dataset)

    assert "UNKNOWN FINGERPRINT" in dataset.output.getvalue()
    assert (tmp_path / "trace" / "manifest.jsonl").exists()


def test_crawl_incremental_manifest_skips_unchanged_sources(tmp_path):
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_url = MODULE.make_content_api_url("/government/publications/example-publication")
    attachment_url = "https://assets.publishing.service.gov.uk/example.csv"
    responses = {
        collection_url: {"links": {"documents": [{"base_path": "/government/publications/example-publication"}]}},
        publication_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {
                "attachments": [
                    {
                        "url": attachment_url,
                        "title": "Meetings",
                        "filename": "example.csv",
                    }
                ]
            },
        },
        attachment_url: b"Minister,Date,Name of organisation or individual,Purpose of meeting\nJane Doe,2024-01-10,Example Org,Policy discussion\n",
    }

    original_load_schema = MODULE.load_schema
    MODULE.load_schema = lambda fingerprint: MODULE.schema_module.schema_from_dict(
        {
            "fingerprint": fingerprint,
            "sheet_type": "data",
            "activity_type": "meetings",
            "subject": {"source": "column"},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [{"type": "strptime", "format": "%Y-%m-%d", "precision": "day"}],
            },
            "mapping": {
                "official_name": 0,
                "counterparty_name": 2,
                "summary": 3,
            },
        }
    )
    try:
        first = DummyDataset(tmp_path)
        first.responses = responses
        MODULE.crawl(first)

        second = DummyDataset(tmp_path)
        second.responses = responses
        MODULE.crawl(second)
    finally:
        MODULE.load_schema = original_load_schema

    manifest_path = tmp_path / "incremental-manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert attachment_url in payload["sources"]
    assert payload["sources"][attachment_url]["status"] == "processed"
    assert not second.emitted


def test_next_unknown_follows_crawler_collection_order(tmp_path, monkeypatch, capsys):
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_early_url = MODULE.make_content_api_url("/government/publications/early-publication")
    publication_late_url = MODULE.make_content_api_url("/government/publications/late-publication")
    early_attachment_url = "https://assets.publishing.service.gov.uk/early.csv"
    late_attachment_url = "https://assets.publishing.service.gov.uk/late.csv"

    class OrderedDataset(DummyDataset):
        def close(self):
            return

    dataset = OrderedDataset(tmp_path)
    dataset.responses = {
        collection_url: {
            "links": {
                "documents": [
                    {"base_path": "/government/publications/early-publication"},
                    {"base_path": "/government/publications/late-publication"},
                ]
            }
        },
        publication_early_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": early_attachment_url, "title": "Early", "filename": "z-last.csv"}]},
        },
        publication_late_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": late_attachment_url, "title": "Late", "filename": "a-first.csv"}]},
        },
        early_attachment_url: b"Alpha,Beta,Gamma\n1,2,3\n",
        late_attachment_url: b"Delta,Epsilon,Zeta\n4,5,6\n",
    }

    monkeypatch.setattr(NEXT_UNKNOWN_MODULE, "iter_crawl_order_sheets", lambda skip_processed=True: iter(()))
    runner_spec = importlib.util.spec_from_file_location(
        "muckrake.crawler.gb.gov_transparency.tools.runner",
        Path("datasets/gb/gov_transparency/tools/runner.py"),
    )
    assert runner_spec is not None
    assert runner_spec.loader is not None
    runner_module = importlib.util.module_from_spec(runner_spec)
    runner_module.__package__ = "muckrake.crawler.gb.gov_transparency.tools"
    sys.modules[runner_spec.name] = runner_module
    runner_spec.loader.exec_module(runner_module)
    monkeypatch.setattr(runner_module, "make_dataset", lambda: dataset)
    monkeypatch.setattr(NEXT_UNKNOWN_MODULE, "iter_crawl_order_sheets", runner_module.iter_crawl_order_sheets)
    exit_code = NEXT_UNKNOWN_MODULE.main()

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resource"].endswith("z-last.csv")


def test_next_unknown_skips_processed_sources_from_incremental_manifest(tmp_path, monkeypatch, capsys):
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_early_url = MODULE.make_content_api_url("/government/publications/early-publication")
    publication_late_url = MODULE.make_content_api_url("/government/publications/late-publication")
    early_attachment_url = "https://assets.publishing.service.gov.uk/early.csv"
    late_attachment_url = "https://assets.publishing.service.gov.uk/late.csv"

    class OrderedDataset(DummyDataset):
        def close(self):
            return

    dataset = OrderedDataset(tmp_path)
    dataset.responses = {
        collection_url: {
            "links": {
                "documents": [
                    {"base_path": "/government/publications/early-publication"},
                    {"base_path": "/government/publications/late-publication"},
                ]
            }
        },
        publication_early_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": early_attachment_url, "title": "Early", "filename": "early.csv"}]},
        },
        publication_late_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": late_attachment_url, "title": "Late", "filename": "late.csv"}]},
        },
        early_attachment_url: b"Alpha,Beta,Gamma\n1,2,3\n",
        late_attachment_url: b"Delta,Epsilon,Zeta\n4,5,6\n",
    }
    early_bytes = dataset.responses[early_attachment_url]
    (tmp_path / "incremental-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "sources": {
                        early_attachment_url: {
                            "url": early_attachment_url,
                            "resource_path": str(tmp_path / "resources" / "example.csv"),
                            "source_signature": f"bytes:{hashlib.sha256(early_bytes).hexdigest()}:{len(early_bytes)}",
                            "schema_registry_signature": MODULE.schema_registry_signature(),
                            "status": "processed",
                            "file_format": "csv",
                        "sheet_fingerprints": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(NEXT_UNKNOWN_MODULE, "iter_crawl_order_sheets", lambda skip_processed=True: iter(()))
    runner_spec = importlib.util.spec_from_file_location(
        "muckrake.crawler.gb.gov_transparency.tools.runner",
        Path("datasets/gb/gov_transparency/tools/runner.py"),
    )
    assert runner_spec is not None
    assert runner_spec.loader is not None
    runner_module = importlib.util.module_from_spec(runner_spec)
    runner_module.__package__ = "muckrake.crawler.gb.gov_transparency.tools"
    sys.modules[runner_spec.name] = runner_module
    runner_spec.loader.exec_module(runner_module)
    monkeypatch.setattr(runner_module, "make_dataset", lambda: dataset)
    monkeypatch.setattr(NEXT_UNKNOWN_MODULE, "iter_crawl_order_sheets", runner_module.iter_crawl_order_sheets)
    exit_code = NEXT_UNKNOWN_MODULE.main()

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resource"].endswith("late.csv")


def test_next_blocker_skips_blocker_clear_sources_from_manifest(tmp_path, monkeypatch, capsys):
    collection_url = MODULE.make_content_api_url("example-collection")
    publication_early_url = MODULE.make_content_api_url("/government/publications/early-publication")
    publication_late_url = MODULE.make_content_api_url("/government/publications/late-publication")
    early_attachment_url = "https://assets.publishing.service.gov.uk/early.csv"
    late_attachment_url = "https://assets.publishing.service.gov.uk/late.csv"

    class OrderedDataset(DummyDataset):
        def close(self):
            return

    dataset = OrderedDataset(tmp_path)
    dataset.responses = {
        collection_url: {
            "links": {
                "documents": [
                    {"base_path": "/government/publications/early-publication"},
                    {"base_path": "/government/publications/late-publication"},
                ]
            }
        },
        publication_early_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": early_attachment_url, "title": "Early", "filename": "early.csv"}]},
        },
        publication_late_url: {
            "title": "Cabinet Office: ministerial meetings, January to March 2024",
            "details": {"attachments": [{"url": late_attachment_url, "title": "Late", "filename": "late.csv"}]},
        },
        early_attachment_url: b"Minister,Date,Name of organisation or individual,Purpose of meeting\nJane Doe,2024-01-10,Example Org,Policy discussion\n",
        late_attachment_url: b"Alpha,Beta,Gamma\n1,2,3\n",
    }
    early_bytes = dataset.responses[early_attachment_url]
    (tmp_path / "incremental-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "sources": {
                    early_attachment_url: {
                        "url": early_attachment_url,
                        "resource_path": str(tmp_path / "resources" / "early.csv"),
                        "source_signature": f"bytes:{hashlib.sha256(early_bytes).hexdigest()}:{len(early_bytes)}",
                        "schema_registry_signature": MODULE.schema_registry_signature(),
                        "status": "blocker_clear",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(NEXT_BLOCKER_MODULE, "make_dataset", lambda: dataset)
    exit_code = NEXT_BLOCKER_MODULE.main()

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resource"].endswith("late.csv")
