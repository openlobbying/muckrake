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


def make_provenance(collection_type: str, attachment_title: str) -> Provenance:
    return Provenance(
        department="cabinet-office",
        collection_type=collection_type,
        publication_title="Cabinet Office: meetings, July to September 2016",
        attachment_title=attachment_title,
        url="https://example.test/source.csv",
        period_start=date(2016, 7, 1),
        period_end=date(2016, 9, 30),
    )


def test_extract_applies_fill_down_and_skips_nil_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "meetings",
            "subject": {"source": "column"},
            "layout": {"fill_down_columns": [0], "nil_return_markers": ["Nil Return"]},
            "date": {"mode": "column", "column": 1, "parsers": [{"type": "month_name_from_period", "precision": "month"}]},
            "mapping": {"official_name": 0, "counterparty_name": 2, "summary": 3},
        }
    )
    provenance = make_provenance("meetings", "Meetings")
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
    assert rows[1]["official_name"] == "Rt Hon Theresa May"
    assert rows[0]["date"] == "2016-07"


def test_extract_resolves_provenance_period_dates():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "provenance_period"},
            "mapping": {"official_name": 0, "summary": 2},
        }
    )
    provenance = make_provenance("gifts", "Gifts")
    sheet = NormalisedSheet(name="Gifts", rows=[["Special adviser", "Date", "Gift"], ["Jane Doe", "Nil return", "Bottle"]])

    rows = extract(sheet, schema, provenance)

    assert rows[0]["start_date"] == "2016-07-01"
    assert rows[0]["end_date"] == "2016-09-30"


def test_extract_can_derive_subject_name_from_provenance():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject": {"source": "provenance"},
            "role_mode": "hosted_by_official",
            "date": {"mode": "column", "column": 0, "parsers": [{"type": "strptime", "format": "%d/%m/%Y", "precision": "day"}]},
            "mapping": {"counterparty_name": 1, "amount": 2},
        }
    )
    provenance = Provenance(
        department="cabinet-office",
        collection_type="hospitality",
        publication_title="Cabinet Office: ministerial gifts hospitality travel and meetings, April to June 2016",
        attachment_title="Rt Hon David Cameron MP guests at chequers, April to June 2016",
        url="https://example.test/source.csv",
        period_start=date(2016, 4, 1),
        period_end=date(2016, 6, 30),
    )
    sheet = NormalisedSheet(name="Guests_at_Chequers", rows=[["Period", "Name", "Total Cost"], ["05/05/2016", "Japanese State Visit", "1260"]])

    rows = extract(sheet, schema, provenance)

    assert rows[0]["official_name"] == "Rt Hon David Cameron MP"


def test_extract_can_derive_subject_name_from_sheet_name():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject": {"source": "sheet_name"},
            "date": {"mode": "column", "column": 0, "parsers": [{"type": "excel_serial", "precision": "day"}]},
            "mapping": {"counterparty_name": 1, "summary": 2},
        }
    )
    provenance = make_provenance("hospitality", "Hospitality")
    sheet = NormalisedSheet(
        name="Peter Housden",
        rows=[
            ["Date", "Organisation Name", "Type of hospitality received"],
            ["40318.0", "Good Work Commission", "Dinner"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["official_name"] == "Peter Housden"


def test_extract_parses_month_year_values():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "column", "column": 1, "parsers": [{"type": "month_name", "precision": "month"}]},
            "mapping": {"official_name": 0, "summary": 2},
        }
    )
    provenance = make_provenance("gifts", "Gifts")
    sheet = NormalisedSheet(name="Gifts", rows=[["Special adviser", "Date", "Gift"], ["Jane Doe", "December 2015", "Scarf"]])

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2015-12"


def test_extract_parses_month_precision_from_iso_datetime_cells():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "column", "column": 1, "parsers": [{"type": "iso_datetime", "precision": "month"}]},
            "mapping": {"official_name": 0, "summary": 2},
        }
    )
    provenance = make_provenance("gifts", "Gifts")
    sheet = NormalisedSheet(name="Gifts", rows=[["Special adviser", "Date", "Gift"], ["Jane Doe", "2016-12-01T00:00:00", "Scarf"]])

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2016-12"


def test_extract_repairs_three_digit_iso_year_using_publication_period():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "meetings",
            "subject": {"source": "column"},
            "date": {"mode": "column", "column": 1, "parsers": [{"type": "iso_datetime", "precision": "day"}]},
            "mapping": {"official_name": 0, "counterparty_name": 2, "summary": 3},
        }
    )
    provenance = Provenance(
        department="beis",
        collection_type="meetings",
        publication_title="BEIS senior officials meetings, April to June 2019",
        attachment_title="Meetings",
        url="https://example.test/source.csv",
        period_start=date(2019, 4, 1),
        period_end=date(2019, 6, 30),
    )
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Permanent secretary", "Date", "Person or organisation that meeting was with", "Purpose of meeting"],
            ["Patrick Vallance", "201-05-16", "The Guardian", "Meeting with the Science Editor"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2019-05-16"


def test_gift_emission_uses_non_numeric_amount_as_fallback_outcome_text():
    entities_module = load_module("gov_transparency_entities_for_extract", "datasets/gb/gov_transparency/entities.py")

    class DummyEntity:
        def __init__(self, schema_name: str):
            self.schema = type("Schema", (), {"name": schema_name})()
            self.id = None
            self.props = {}

        def add(self, key, value):
            self.props.setdefault(key, []).append(value)

    class DummyDataset:
        def __init__(self):
            self.emitted = []

        def make(self, schema_name: str):
            return DummyEntity(schema_name)

        def make_id(self, *parts, **kwargs):
            return "::".join(str(p) for p in parts) or "id"

        def emit(self, entity):
            self.emitted.append(entity)

    dataset = DummyDataset()
    provenance = Provenance(
        department="bis",
        collection_type="special-advisers-gifts",
        publication_title="Special advisers gifts received: July to September 2012",
        attachment_title="gifts",
        url="https://example.test/source.csv",
        period_start=date(2012, 7, 1),
        period_end=date(2012, 9, 30),
    )
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "column", "column": 1, "parsers": [{"type": "iso_datetime", "precision": "day"}]},
            "mapping": {"official_name": 0, "counterparty_name": 2, "summary": 3, "amount": 4},
        }
    )
    row = {
        "official_name": "Giles Wilkes",
        "counterparty_name": "EngineeringUK",
        "summary": "Large framed photo",
        "amount": "Held by the Department",
        "date": "2012-09-25",
        "date_precision": "day",
        "row_index": 1,
        "sheet_name": "default",
    }

    entities_module.emit_entities(dataset, row, provenance, schema)

    gift = next(entity for entity in dataset.emitted if entity.schema.name == "Gift")
    assert gift.props["description"] == ["Held by the Department"]


def test_extract_parses_ordinal_day_dates_and_day_ranges():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "travel",
            "subject": {"source": "column"},
            "layout": {"fill_down_columns": [0], "nil_return_markers": ["Nil Return"]},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [
                    {"type": "strptime", "format": "%d %B %Y", "precision": "day"},
                    {"type": "day_range", "precision": "day"},
                ],
            },
            "mapping": {"official_name": 0, "location": 2},
        }
    )
    provenance = make_provenance("travel", "Travel")
    sheet = NormalisedSheet(
        name="Travel",
        rows=[
            ["Minister", "Date(s) of trip", "Destination"],
            ["Jane Doe", "14th October 2015", "Rome"],
            ["Jane Doe", "02-06 September", "Beijing"],
            ["Jane Doe", "4 to 11 May", "Auckland"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["date"] == "2015-10-14"
    assert rows[1]["start_date"] == "2016-09-02"
    assert rows[1]["end_date"] == "2016-09-06"
    assert rows[2]["start_date"] == "2016-05-04"
    assert rows[2]["end_date"] == "2016-05-11"


def test_extract_parses_slash_separated_ordinal_day_ranges():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "travel",
            "subject": {"source": "column"},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [{"type": "day_range", "precision": "day"}],
            },
            "mapping": {"official_name": 0, "location": 2},
        }
    )
    provenance = make_provenance("travel", "Travel")
    sheet = NormalisedSheet(
        name="Travel",
        rows=[
            ["Minister", "Date(s) of trip", "Destination"],
            ["Jane Doe", "11th/12th June 2016", "Paris"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["start_date"] == "2016-06-11"
    assert rows[0]["end_date"] == "2016-06-12"


def test_extract_parses_mixed_day_and_month_dates_with_ordered_rules():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject": {"source": "column"},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [
                    {"type": "strptime", "format": "%d-%b-%y", "precision": "day"},
                    {"type": "month_name_from_period", "precision": "month"},
                ],
            },
            "mapping": {"official_name": 0, "counterparty_name": 2, "summary": 3},
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


def test_extract_parses_day_month_values_using_publication_period_year():
    schema = schema_from_dict(
        {
            "fingerprint": "abc",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject": {"source": "column"},
            "layout": {"fill_down_columns": [0]},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [
                    {"type": "iso_datetime", "precision": "day"},
                    {"type": "day_range", "precision": "day"},
                    {"type": "month_name_from_period", "precision": "month"},
                ],
            },
            "mapping": {"official_name": 0, "counterparty_name": 2, "summary": 3},
        }
    )
    provenance = Provenance(
        department="ago",
        collection_type="hospitality",
        publication_title="AGO hospitality, October to December 2013",
        attachment_title="Hospitality",
        url="https://example.test/source.csv",
        period_start=date(2013, 10, 1),
        period_end=date(2013, 12, 31),
    )
    sheet = NormalisedSheet(
        name="default",
        rows=[
            ["Minister", "Date", "Name of organisation", "Type of hospitality"],
            ["Attorney General Dominic Grieve QC MP", "", "", ""],
            ["", "10-Oct", "The Telegraph", "Lunch"],
            ["", "05-Nov", "Liberty", "Lunch"],
        ],
    )

    rows = extract(sheet, schema, provenance)

    assert rows[0]["official_name"] == "Attorney General Dominic Grieve QC MP"
    assert rows[0]["date"] == "2013-10-10"
    assert rows[1]["date"] == "2013-11-05"


def test_extract_skips_nil_only_sparse_hospitality_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "53ec96c8875a4269",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "subject": {"source": "column"},
            "layout": {"data_start_offset": 0},
            "date": {"mode": "provenance_period"},
            "mapping": {"official_name": 0, "summary": 1},
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
