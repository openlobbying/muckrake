from pathlib import Path
import importlib.util
import json
import sys


SCHEMA_PATH = Path("datasets/gb/gov_transparency/schema.py")
SCHEMA_SPEC = importlib.util.spec_from_file_location("gov_transparency_schema", SCHEMA_PATH)
assert SCHEMA_SPEC is not None
assert SCHEMA_SPEC.loader is not None
SCHEMA_MODULE = importlib.util.module_from_spec(SCHEMA_SPEC)
sys.modules[SCHEMA_SPEC.name] = SCHEMA_MODULE
SCHEMA_SPEC.loader.exec_module(SCHEMA_MODULE)

load_schema = SCHEMA_MODULE.load_schema
schema_from_dict = SCHEMA_MODULE.schema_from_dict
validate_schema = SCHEMA_MODULE.validate_schema

NORMALISE_PATH = Path("datasets/gb/gov_transparency/normalise.py")
NORMALISE_SPEC = importlib.util.spec_from_file_location("gov_transparency_normalise_for_schema", NORMALISE_PATH)
assert NORMALISE_SPEC is not None
assert NORMALISE_SPEC.loader is not None
NORMALISE_MODULE = importlib.util.module_from_spec(NORMALISE_SPEC)
sys.modules[NORMALISE_SPEC.name] = NORMALISE_MODULE
NORMALISE_SPEC.loader.exec_module(NORMALISE_MODULE)
NormalisedSheet = NORMALISE_MODULE.NormalisedSheet


def meetings_schema_dict() -> dict:
    return {
        "fingerprint": "abc123",
        "sheet_type": "data",
        "activity_type": "meetings",
        "subject": {"source": "column"},
        "layout": {"fill_down_columns": [0]},
        "date": {
            "mode": "column",
            "column": 1,
            "parsers": [{"type": "strptime", "format": "%d/%m/%Y", "precision": "day"}],
        },
        "mapping": {"official_name": 0, "summary": 2},
    }


def test_load_schema_reads_json_from_schemas_dir(tmp_path, monkeypatch):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "abc123.json").write_text(json.dumps(meetings_schema_dict()), encoding="utf-8")
    monkeypatch.setattr(SCHEMA_MODULE, "SCHEMAS_DIR", schema_dir)

    schema = load_schema("abc123")

    assert schema is not None
    assert schema.fingerprint == "abc123"
    assert schema.mapping["official_name"] == 0


def test_schema_from_dict_rejects_legacy_schema_shape_at_runtime():
    try:
        schema_from_dict(
            {
                "fingerprint": "abc123",
                "sheet_type": "data",
                "activity_type": "meetings",
                "date_source": "column",
                "date_column": 1,
                "date_format": "%d/%m/%Y",
                "date_precision": "day",
                "columns": {"subject_name": 0, "activity_description": 2},
            }
        )
    except ValueError as exc:
        assert "Unknown schema fields" in str(exc)
    else:
        raise AssertionError("Expected runtime schema loader to reject legacy schema fields")


def test_validate_schema_accepts_valid_sheet():
    schema = schema_from_dict(meetings_schema_dict())
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[["Minister", "Date", "Purpose of meeting"], ["Jane Doe", "12/01/2024", "Example meeting"]],
    )

    validate_schema(schema, sheet)


def test_validate_schema_rejects_invalid_later_date_even_if_first_row_is_valid():
    schema = schema_from_dict(meetings_schema_dict())
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "12/01/2024", "Example meeting"],
            ["Jane Doe", "not-a-date", "Example meeting"],
        ],
    )

    try:
        validate_schema(schema, sheet)
    except ValueError as exc:
        assert "Cannot parse date value" in str(exc) or "Unrecognised" in str(exc)
    else:
        raise AssertionError("Expected validate_schema to fail on an invalid later date row")


def test_validate_schema_accepts_multiple_valid_date_rows():
    schema = schema_from_dict(meetings_schema_dict())
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "12/01/2024", "Example meeting"],
            ["Jane Doe", "13/01/2024", "Another meeting"],
        ],
    )

    validate_schema(schema, sheet)


def test_validate_schema_accepts_mixed_parser_rules():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
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
            "mapping": {"official_name": 0, "summary": 2},
        }
    )
    sheet = NormalisedSheet(
        name="Hospitality",
        rows=[["Minister", "Date", "Gift"], ["Jane Doe", "May-11", "Lunch"]],
    )

    validate_schema(schema, sheet)


def test_validate_schema_rejects_blank_end_date_on_later_row():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "travel",
            "subject": {"source": "column"},
            "date": {
                "mode": "column_range",
                "column": 1,
                "end_column": 2,
                "parsers": [{"type": "strptime", "format": "%Y-%m-%d", "precision": "day"}],
            },
            "mapping": {"official_name": 0, "location": 3},
        }
    )
    sheet = NormalisedSheet(
        name="Travel",
        rows=[
            ["Minister", "Start", "End", "Destination"],
            ["Jane Doe", "2024-01-10", "2024-01-11", "Paris"],
            ["Jane Doe", "2024-01-12", "", "Rome"],
        ],
    )

    try:
        validate_schema(schema, sheet)
    except ValueError as exc:
        assert "no data rows" not in str(exc)
    else:
        raise AssertionError("Expected validate_schema to fail on a later blank end date")


def test_validate_schema_accepts_provenance_period_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "provenance_period"},
            "mapping": {"official_name": 0, "summary": 1},
        }
    )
    sheet = NormalisedSheet(name="Gifts", rows=[["Minister", "Gift"], ["Jane Doe", "Nil return"], ["John Doe", "Nil return"]])

    validate_schema(schema, sheet)


def test_validate_schema_accepts_nil_only_data_rows_when_date_column_has_nil_marker():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "layout": {"fill_down_columns": [0], "nil_return_markers": ["-"]},
            "date": {
                "mode": "column",
                "column": 1,
                "parsers": [{"type": "iso_datetime", "precision": "day"}, {"type": "month_name_from_period", "precision": "month"}],
            },
            "mapping": {"official_name": 0, "summary": 2, "counterparty_name": 4, "amount": 5, "outcome_text": 6},
        }
    )
    sheet = NormalisedSheet(
        name="Gifts",
        rows=[
            ["Minister", "Date", "Gift", "Given or received", "Who gift was given to or received from", "Value", "Outcome"],
            ["Anti-Corruption Champion - Nil return", "-", "-", "-", "-", "-", "-"],
        ],
    )

    validate_schema(schema, sheet)


def test_validate_schema_rejects_missing_data_rows():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "meetings",
            "subject": {"source": "column"},
            "date": {"mode": "provenance_period"},
            "mapping": {"official_name": 0, "summary": 2},
        }
    )
    sheet = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Purpose of meeting"], ["", "", ""], ["", "", ""]])

    try:
        validate_schema(schema, sheet)
    except ValueError as exc:
        assert "has no data rows" in str(exc)
    else:
        raise AssertionError("Expected validate_schema to fail when no data rows exist")


def test_schema_from_dict_adds_default_nil_markers_for_data_sheets():
    schema = schema_from_dict(
        {
            "fingerprint": "abc123",
            "sheet_type": "data",
            "activity_type": "gifts",
            "subject": {"source": "column"},
            "date": {"mode": "provenance_period"},
            "mapping": {"official_name": 0, "summary": 1},
        }
    )

    assert "Nil Return" in schema.layout.nil_return_markers
    assert "None in this period" in schema.layout.nil_return_markers


def test_schema_from_dict_requires_activity_type_for_data_sheets():
    try:
        schema_from_dict({"fingerprint": "abc123", "sheet_type": "data", "mapping": {"official_name": 0}})
    except ValueError as exc:
        assert "activity_type" in str(exc)
    else:
        raise AssertionError("Expected schema_from_dict to reject data schemas without activity_type")


def test_schema_from_dict_rejects_unknown_fields():
    try:
        schema_from_dict({"fingerprint": "abc123", "sheet_type": "data", "activity_type": "meetings", "mapping": {"official_name": 0}, "mystery": True})
    except ValueError as exc:
        assert "Unknown schema fields" in str(exc)
    else:
        raise AssertionError("Expected schema_from_dict to reject unknown fields")


def test_schema_from_dict_rejects_unsupported_activity_type():
    try:
        schema_from_dict({"fingerprint": "abc123", "sheet_type": "data", "activity_type": "other", "mapping": {"official_name": 0}})
    except ValueError as exc:
        assert "Unsupported activity_type" in str(exc)
    else:
        raise AssertionError("Expected schema_from_dict to reject unsupported activity types")


def test_schema_from_dict_requires_reason_for_non_data_sheets():
    try:
        schema_from_dict({"fingerprint": "abc123", "sheet_type": "notes"})
    except ValueError as exc:
        assert "reason" in str(exc)
    else:
        raise AssertionError("Expected schema_from_dict to require a reason for non-data sheets")


def test_schema_from_dict_rejects_activity_type_for_notes_sheets():
    try:
        schema_from_dict({"fingerprint": "abc123", "sheet_type": "notes", "reason": "Explanatory notes sheet.", "activity_type": "meetings"})
    except ValueError as exc:
        assert "activity_type" in str(exc)
    else:
        raise AssertionError("Expected schema_from_dict to reject non-data schemas with activity_type")


def test_schema_from_dict_accepts_reason_for_notes_sheets():
    schema = schema_from_dict({"fingerprint": "abc123", "sheet_type": "notes", "reason": "Explanatory notes sheet."})

    assert schema.reason == "Explanatory notes sheet."
    assert schema.activity_type is None
