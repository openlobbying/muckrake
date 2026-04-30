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


extract_module = load_module("gov_transparency_extract", "datasets/gb/gov_transparency/extract.py")
schema_module = load_module("gov_transparency_schema_for_extract", "datasets/gb/gov_transparency/schema.py")
types_module = load_module("gov_transparency_types_for_extract", "datasets/gb/gov_transparency/types.py")
normalise_module = load_module("gov_transparency_normalise_for_extract", "datasets/gb/gov_transparency/normalise.py")

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
                "subject_name": 0,
                "counterpart_name": 2,
                "activity_description": 3,
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
    assert rows[1]["subject_name"] == "Rt Hon Theresa May"
    assert rows[0]["date"] == "2016-07"


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
            "columns": {"subject_name": 0, "activity_description": 2},
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

    assert rows[0]["start_date"] == "2015-10-01"
    assert rows[0]["end_date"] == "2015-12-31"


def test_extract_can_derive_subject_name_from_provenance():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject_name_source": "provenance",
            "reverse_roles": True,
            "data_start_offset": 1,
            "fill_down_columns": [],
            "date_source": "column",
            "date_column": 0,
            "date_format": "%d/%m/%Y",
            "date_precision": "day",
            "columns": {"counterpart_name": 1, "amount": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="hospitality",
        publication_title="Cabinet Office: ministerial gifts, hospitality, travel and meetings, April to June 2016",
        attachment_title="Rt Hon David Cameron MP guests at chequers, April to June 2016",
        url="https://example.test/source.csv",
        period_start=date(2016, 4, 1),
        period_end=date(2016, 6, 30),
    )
    sheet = NormalisedSheet(
        name="Guests_at_Chequers",
        rows=[
            ["Period", "Name", "Total Cost"],
            ["05/05/2016", "Japanese State Visit", "1260"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["subject_name"] == "Rt Hon David Cameron MP"


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
            "columns": {"subject_name": 0, "activity_description": 2},
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

    assert rows[0]["date"] == "2015-12"


def test_extract_parses_month_precision_from_iso_datetime_cells():
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
            "columns": {"subject_name": 0, "activity_description": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="gifts",
        publication_title="Cabinet Office: gifts, October to December 2016",
        attachment_title="Gifts",
        url="https://example.test/source.ods",
        period_start=date(2016, 10, 1),
        period_end=date(2016, 12, 31),
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Special adviser", "Date", "Gift"],
            ["Jane Doe", "2016-12-01T00:00:00", "Scarf"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2016-12"


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
            "columns": {"subject_name": 0, "location": 2},
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
            ["Jane Doe", "4 to 11 May", "Auckland"],
            ["Jane Doe", "13 June - 16th June", "Ottawa"],
            ["Jane Doe", "12 - 17 July 11", "Sydney"],
            ["Jane Doe", "27 June - 2 July 2011", "Seoul"],
            ["Jane Doe", "8/11/16 - 11/11/16", "Seoul"],
            ["Jane Doe", "17 May 2016 - 20 May 2016", "Port of Spain"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2015-10-14"
    assert rows[1]["start_date"] == "2016-09-02"
    assert rows[1]["end_date"] == "2016-09-06"
    assert rows[2]["start_date"] == "2016-05-04"
    assert rows[2]["end_date"] == "2016-05-11"
    assert rows[3]["start_date"] == "2016-06-13"
    assert rows[3]["end_date"] == "2016-06-16"
    assert rows[4]["start_date"] == "2011-07-12"
    assert rows[4]["end_date"] == "2011-07-17"
    assert rows[5]["start_date"] == "2011-06-27"
    assert rows[5]["end_date"] == "2011-07-02"
    assert rows[6]["start_date"] == "2016-11-08"
    assert rows[6]["end_date"] == "2016-11-11"
    assert rows[7]["start_date"] == "2016-05-17"
    assert rows[7]["end_date"] == "2016-05-20"


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
                "subject_name": 0,
                "counterpart_name": 2,
                "activity_description": 3,
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

    assert rows[0]["date"] == "2011-02"
    assert rows[0]["date_precision"] == "month"
    assert rows[1]["date"] == "2011-03-19"
    assert rows[1]["date_precision"] == "day"


def test_extract_skips_nil_only_sparse_hospitality_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "53ec96c8875a4269",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "data_start_offset": 0,
            "fill_down_columns": [],
            "date_source": "none",
            "date_precision": "quarter",
            "columns": {
                "subject_name": 0,
                "activity_description": 1,
            },
        }
    )
    provenance = Provenance(
        department="ago",
        collection_type="hospitality",
        publication_title="AGO hospitality, April to June 2012",
        attachment_title="Hospitality",
        url="https://example.test/source.csv",
        period_start=date(2012, 4, 1),
        period_end=date(2012, 6, 30),
    )
    sheet = NormalisedSheet(
        name="default",
        rows=[
            ["Minister", "", ""],
            ["Attorney General Dominic Grieve QC MP", "Nil return", "Nil return"],
            ["", "", ""],
            ["Solicitor General Edward Garnier QC MP", "Nil return", "Nil return"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows == []
