from datetime import date
from pathlib import Path
import importlib.util
import sys


def load_module(name: str, relative_path: str):
    path = Path(relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


extract_module = load_module("gov_transparency_extract", "datasets/gb/gov-transparency/extract.py")
schema_module = load_module("gov_transparency_schema_for_extract", "datasets/gb/gov-transparency/schema.py")
types_module = load_module("gov_transparency_types_for_extract", "datasets/gb/gov-transparency/types.py")
normalise_module = load_module("gov_transparency_normalise_for_extract", "datasets/gb/gov-transparency/normalise.py")

extract = extract_module.extract
schema_from_dict = schema_module.schema_from_dict
Provenance = types_module.Provenance
NormalisedSheet = normalise_module.NormalisedSheet


def test_extract_applies_fill_down_and_skips_nil_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "meetings",
            "data_start_offset": 1,
            "fill_down_columns": [0],
            "nil_return_markers": ["Nil Return"],
            "date_source": "column",
            "date_column": 1,
            "date_precision": "month",
            "columns": {
                "minister_name": 0,
                "counterpart_raw": 2,
                "purpose": 3,
            },
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="meetings",
        publication_title="Cabinet Office: meetings, July to September 2016",
        attachment_title="Meetings",
        url="https://example.test/source.ods",
        period_start=date(2016, 7, 1),
        period_end=date(2016, 9, 30),
    )
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Name of organisation or individual", "Purpose of meeting"],
            ["Rt Hon Theresa May", "July", "SoftBank", "Acquisition of ARM"],
            ["", "August", "British Red Cross", "The organisation's work"],
            ["", "Nil Return", "Nil Return", "Nil Return"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert len(rows) == 2
    assert rows[1]["minister_name"] == "Rt Hon Theresa May"
    assert rows[0]["date_from"] == date(2016, 7, 1)
    assert rows[0]["date_to"] == date(2016, 7, 31)


def test_extract_resolves_quarter_dates_from_provenance():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return"],
            "date_source": "none",
            "date_precision": "quarter",
            "columns": {"minister_name": 0, "gift_description": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="gifts",
        publication_title="Cabinet Office: gifts, October to December 2015",
        attachment_title="Gifts",
        url="https://example.test/source.xlsx",
        period_start=date(2015, 10, 1),
        period_end=date(2015, 12, 31),
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Special adviser", "Date", "Gift"],
            ["Jane Doe", "Nil return", "Bottle"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date_from"] == date(2015, 10, 1)
    assert rows[0]["date_to"] == date(2015, 12, 31)


def test_extract_parses_month_year_values():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return"],
            "date_source": "column",
            "date_column": 1,
            "date_precision": "month",
            "columns": {"minister_name": 0, "gift_description": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="gifts",
        publication_title="Cabinet Office: gifts, October to December 2015",
        attachment_title="Gifts",
        url="https://example.test/source.xlsx",
        period_start=date(2015, 10, 1),
        period_end=date(2015, 12, 31),
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Special adviser", "Date", "Gift"],
            ["Jane Doe", "December 2015", "Scarf"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date_from"] == date(2015, 12, 1)
    assert rows[0]["date_to"] == date(2015, 12, 31)


def test_extract_parses_ordinal_day_dates_and_day_ranges():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "travel",
            "data_start_offset": 1,
            "fill_down_columns": [0],
            "nil_return_markers": ["Nil Return"],
            "date_source": "column",
            "date_column": 1,
            "date_format": "%d %B %Y",
            "date_precision": "day",
            "columns": {"minister_name": 0, "destination": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="travel",
        publication_title="Cabinet Office: travel, July to September 2016",
        attachment_title="Travel",
        url="https://example.test/source.ods",
        period_start=date(2016, 7, 1),
        period_end=date(2016, 9, 30),
    )
    sheet = NormalisedSheet(
        name="Travel",
        rows=[
            ["Minister", "Date(s) of trip", "Destination"],
            ["Jane Doe", "14th October 2015", "Rome"],
            ["Jane Doe", "02-06 September", "Beijing"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == date(2015, 10, 14)
    assert rows[1]["date_from"] == date(2016, 9, 2)
    assert rows[1]["date_to"] == date(2016, 9, 6)


def test_extract_parses_mixed_day_or_month_dates():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return", "Nil return"],
            "date_source": "column",
            "date_column": 1,
            "date_precision": "day_or_month",
            "columns": {
                "minister_name": 0,
                "counterpart_raw": 2,
                "gift_description": 3,
            },
        }
    )
    provenance = Provenance(
        department="ago",
        collection_type="hospitality",
        publication_title="AGO hospitality, January to March 2011",
        attachment_title="Hospitality",
        url="https://example.test/source.csv",
        period_start=date(2011, 1, 1),
        period_end=date(2011, 3, 31),
    )
    sheet = NormalisedSheet(
        name="Hospitality",
        rows=[
            ["Minister", "Date", "Name of organisation", "Type of Hospitality Received"],
            ["Attorney General Dominic Grieve QC MP", "Feb-11", "Telegraph Media Group", "Lunch"],
            ["Attorney General Dominic Grieve QC MP", "19-Mar-11", "Lunch 4 Life", "Dinner"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date_from"] == date(2011, 2, 1)
    assert rows[0]["date_to"] == date(2011, 2, 28)
    assert rows[0]["date_precision"] == "month"
    assert rows[1]["date"] == date(2011, 3, 19)
    assert rows[1]["date_precision"] == "day"
