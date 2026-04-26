import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from datasets.gb.meetings.common import Publication, Period, TableSource, iter_publication_tables
from datasets.gb.meetings.validation import MeetingsValidation


class DummyHtmlDataset:
    def __init__(self, pages, resource_path: Path | None = None):
        self.pages = pages
        self.resource_path = resource_path

    def fetch_html(self, url: str, cache_days: int = 30, absolute_links: bool = True):
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    def fetch_resource(self, name: str, url: str):
        if self.resource_path is None:
            raise AttributeError("fetch_resource")
        return self.resource_path


def make_source(category: str, frame: pd.DataFrame) -> TableSource:
    return TableSource(
        publication=Publication(
            url="https://www.gov.uk/government/publications/example",
            title="January to March 2024 example",
            period=Period(start=datetime(2024, 1, 1).date(), end=datetime(2024, 3, 31).date()),
        ),
        category=category,
        source_url="https://assets.publishing.service.gov.uk/example.csv",
        title="example",
        file_name="example.csv",
        frame=frame,
    )


def test_iter_publication_tables_logs_unknown_category(tmp_path, caplog):
    from lxml import html

    path = tmp_path / "unknown.csv"
    path.write_text("Foo,Bar\n1,2\n", encoding="utf-8")

    dataset = DummyHtmlDataset(
        {
            "https://example.com/collection": html.fromstring(
                '<a href="https://www.gov.uk/government/publications/example-publication">Example publication</a>'
            ),
            "https://www.gov.uk/government/publications/example-publication": html.fromstring(
                '<a href="https://assets.publishing.service.gov.uk/media/example/unknown.csv">Unknown attachment</a>'
            ),
        }
        ,
        resource_path=path,
    )
    validator = MeetingsValidation()

    with caplog.at_level(logging.WARNING):
        tables = list(
            iter_publication_tables(
                dataset,
                ["https://example.com/collection"],
                validator=validator,
                department_name="Department Example",
            )
        )

    assert tables == []
    assert validator.unknown_categories == 1
    assert "Meetings table skipped with unknown category" in caplog.text


def test_validation_logs_weak_mapping_and_zero_canonical_source(caplog):
    validator = MeetingsValidation()
    source = make_source(
        "meetings",
        pd.DataFrame([
            {"date": "2024-01-10", "organisation met": "Example Org"},
        ]),
    )

    with caplog.at_level(logging.INFO):
        source_validation = validator.start_source("Department Example", source)
        validator.finish_source(source_validation)

    assert validator.weak_field_mappings == 1
    assert validator.zero_canonical_sources == 1
    assert "Meetings source has weak field mapping" in caplog.text
    assert "Meetings source produced no canonical records" in caplog.text


def test_validation_summary_logs_aggregate_counts(caplog):
    validator = MeetingsValidation()
    validator.unknown_categories = 2
    validator.zero_canonical_sources = 1

    with caplog.at_level(logging.INFO):
        validator.log_summary()

    assert "Meetings validation summary" in caplog.text
    assert "unknown_categories=2" in caplog.text
    assert "zero_canonical=1" in caplog.text
