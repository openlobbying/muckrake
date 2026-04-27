from pathlib import Path
import importlib.util
import sys
from datetime import date
import json
import logging
from io import StringIO

from org_id import make_hashed_id


MODULE_PATH = Path("datasets/gb/gov-transparency/crawler.py")
SPEC = importlib.util.spec_from_file_location(
    "muckrake.crawler.gb.gov-transparency.crawler",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
MODULE.__package__ = "muckrake.crawler.gb.gov-transparency"
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

parse_period = MODULE.parse_period


class DummyDataset:
    def __init__(self, tmp_path):
        self._data = {"collections": ["example-collection"], "fail_on_unknown": False}
        self.prefix = "gb-gov"
        self.emitted = []
        self.resources_path = tmp_path / "resources"
        self.resources_path.mkdir(parents=True, exist_ok=True)
        self.output = StringIO()
        self.log = logging.getLogger(f"gov-transparency-test-{id(self)}")
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


def test_crawl_emits_entities_for_known_schema(tmp_path):
    dataset = DummyDataset(tmp_path)
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

    MODULE.crawl(dataset)

    assert any(entity.schema.name == "Event" for entity in dataset.emitted)
    assert any(entity.schema.name == "Person" for entity in dataset.emitted)


def test_crawl_reports_unknown_fingerprint(tmp_path):
    dataset = DummyDataset(tmp_path)
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
