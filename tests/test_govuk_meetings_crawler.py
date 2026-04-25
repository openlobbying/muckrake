from datetime import date

from datasets.gb.meetings.crawler import get_departments
from datasets.gb.meetings.govuk_ministerial import record_in_date_range


class DummyDataset:
    def __init__(self, departments):
        self._data = {"departments": departments}


def test_get_departments_skips_empty_collection_urls():
    dataset = DummyDataset(
        [
            {"name": "Department A", "collection_urls": []},
            {"name": "Department B", "collection_urls": ["https://example.com/collection"]},
        ]
    )

    departments = list(get_departments(dataset))

    assert departments == [
        {
            "name": "Department B",
            "collection_urls": ["https://example.com/collection"],
            "start_date": None,
            "end_date": None,
        }
    ]


def test_get_departments_parses_date_bounds():
    dataset = DummyDataset(
        [
            {
                "name": "Department Example",
                "collection_urls": ["https://example.com/collection"],
                "start_date": "2021-09-15",
                "end_date": "2024-07-01",
            }
        ]
    )

    department = next(iter(get_departments(dataset)))

    assert department["start_date"] == date(2021, 9, 15)
    assert department["end_date"] == date(2024, 7, 1)


def test_record_in_date_range_excludes_records_before_start_date():
    record = {"date": "2020-01-10", "period": None}

    assert not record_in_date_range(record, start_date=date(2021, 1, 1), end_date=None)


def test_record_in_date_range_excludes_records_on_or_after_end_date():
    record = {"date": "2024-07-01", "period": None}

    assert not record_in_date_range(record, start_date=None, end_date=date(2024, 7, 1))


def test_record_in_date_range_includes_records_within_bounds():
    record = {"date": "2023-05-10", "period": None}

    assert record_in_date_range(
        record,
        start_date=date(2021, 9, 15),
        end_date=date(2024, 7, 1),
    )
