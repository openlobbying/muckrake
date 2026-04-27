from pathlib import Path
import importlib.util
import json
import sys


SCHEMA_PATH = Path("datasets/gb/gov-transparency/schema.py")
SCHEMA_SPEC = importlib.util.spec_from_file_location("gov_transparency_schema", SCHEMA_PATH)
assert SCHEMA_SPEC is not None
assert SCHEMA_SPEC.loader is not None
SCHEMA_MODULE = importlib.util.module_from_spec(SCHEMA_SPEC)
sys.modules[SCHEMA_SPEC.name] = SCHEMA_MODULE
SCHEMA_SPEC.loader.exec_module(SCHEMA_MODULE)

load_schema = SCHEMA_MODULE.load_schema
schema_from_dict = SCHEMA_MODULE.schema_from_dict
validate_schema = SCHEMA_MODULE.validate_schema

NORMALISE_PATH = Path("datasets/gb/gov-transparency/normalise.py")
NORMALISE_SPEC = importlib.util.spec_from_file_location("gov_transparency_normalise_for_schema", NORMALISE_PATH)
assert NORMALISE_SPEC is not None
assert NORMALISE_SPEC.loader is not None
NORMALISE_MODULE = importlib.util.module_from_spec(NORMALISE_SPEC)
sys.modules[NORMALISE_SPEC.name] = NORMALISE_MODULE
NORMALISE_SPEC.loader.exec_module(NORMALISE_MODULE)
NormalisedSheet = NORMALISE_MODULE.NormalisedSheet


def test_load_schema_reads_json_from_schemas_dir(tmp_path, monkeypatch):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "abc123.json").write_text(
        json.dumps(
            {
                "fingerprint": "abc123",
                "sheet_type": "data",
                "activity_type": "meetings",
                "data_start_offset": 1,
                "fill_down_columns": [0],
                "nil_return_markers": ["Nil Return"],
                "date_source": "column",
                "date_column": 1,
                "date_format": "%d/%m/%Y",
                "date_precision": "day",
                "columns": {"minister_name": 0, "purpose": 2},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SCHEMA_MODULE, "SCHEMAS_DIR", schema_dir)

    schema = load_schema("abc123")

    assert schema is not None
    assert schema.fingerprint == "abc123"
    assert schema.columns["minister_name"] == 0


def test_validate_schema_accepts_valid_sheet():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "meetings",
            "data_start_offset": 1,
            "fill_down_columns": [0],
            "nil_return_markers": ["Nil Return"],
            "date_source": "column",
            "date_column": 1,
            "date_format": "%d/%m/%Y",
            "date_precision": "day",
            "columns": {"minister_name": 0, "purpose": 2},
        }
    )
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "12/01/2024", "Example meeting"],
        ],
    )

    validate_schema(schema, sheet)


def test_validate_schema_rejects_missing_parseable_dates():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "meetings",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return"],
            "date_source": "column",
            "date_column": 1,
            "date_format": "%d/%m/%Y",
            "date_precision": "day",
            "columns": {"minister_name": 0, "purpose": 2},
        }
    )
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "not-a-date", "Example meeting"],
        ],
    )

    try:
        validate_schema(schema, sheet)
    except ValueError as exc:
        assert "Unrecognised day value" in str(exc) or "parseable date" in str(exc)
    else:
        raise AssertionError("Expected validate_schema to fail on invalid date values")


def test_validate_schema_accepts_mixed_day_or_month_dates():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "hospitality",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return", "Nil return"],
            "date_source": "column",
            "date_column": 1,
            "date_precision": "day_or_month",
            "columns": {"minister_name": 0, "gift_description": 2},
        }
    )
    sheet = NormalisedSheet(
        name="Hospitality",
        rows=[
            ["Minister", "Date", "Gift"],
            ["Jane Doe", "May-11", "Lunch"],
        ],
    )

    validate_schema(schema, sheet)


def test_validate_schema_accepts_nil_only_rows_when_layout_is_valid():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "gifts",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return", "Nil return", "None in this period"],
            "date_source": "none",
            "date_precision": "quarter",
            "columns": {"minister_name": 0, "gift_description": 1},
        }
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Minister", "Gift"],
            ["Jane Doe", "Nil return"],
            ["John Doe", "Nil return"],
        ],
    )

    validate_schema(schema, sheet)


def test_validate_schema_rejects_missing_data_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "meetings",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return"],
            "date_source": "none",
            "date_precision": "quarter",
            "columns": {"minister_name": 0, "purpose": 2},
        }
    )
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["", "", ""],
            ["", "", ""],
        ],
    )

    try:
        validate_schema(schema, sheet)
    except ValueError as exc:
        assert "has no data rows" in str(exc)
    else:
        raise AssertionError("Expected validate_schema to fail when no data rows exist")


def test_validate_schema_accepts_nil_only_rows_with_blank_date_column():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "gifts",
            "data_start_offset": 1,
            "fill_down_columns": [],
            "nil_return_markers": ["Nil Return", "Nil return", "None in this period"],
            "date_source": "column",
            "date_column": 3,
            "date_precision": "month",
            "columns": {"minister_name": 0, "gift_description": 1, "outcome": 6},
        }
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Minister", "Gifts received over £140", "Gifts given over £140", "Date received/given", "From/to", "Value", "Outcome"],
            ["Jane Doe", "Nil return", "None in this period", "", "", "", ""],
        ],
    )

    validate_schema(schema, sheet)
