from pathlib import Path
import importlib.util
import sys


MODULE_PATH = Path("datasets/gb/gov_transparency/fingerprint.py")
SPEC = importlib.util.spec_from_file_location("gov_transparency_fingerprint", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

detect_header_row = MODULE.detect_header_row
fingerprint = MODULE.fingerprint
looks_like_label = MODULE.looks_like_label

NORMALISE_PATH = Path("datasets/gb/gov_transparency/normalise.py")
NORMALISE_SPEC = importlib.util.spec_from_file_location("gov_transparency_normalise_for_fp", NORMALISE_PATH)
assert NORMALISE_SPEC is not None
assert NORMALISE_SPEC.loader is not None
NORMALISE_MODULE = importlib.util.module_from_spec(NORMALISE_SPEC)
sys.modules[NORMALISE_SPEC.name] = NORMALISE_MODULE
NORMALISE_SPEC.loader.exec_module(NORMALISE_MODULE)
NormalisedSheet = NORMALISE_MODULE.NormalisedSheet


def test_detect_header_row_skips_title_rows():
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Cabinet Office meetings", "", ""],
            ["January to March 2024", "", ""],
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "12/01/2024", "Example"],
        ],
    )

    assert detect_header_row(sheet) == 2


def test_fingerprint_is_stable_for_same_headers_with_different_rows():
    left = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["Jane Doe", "12/01/2024", "Example"],
        ],
    )
    right = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Purpose of meeting"],
            ["John Smith", "13/01/2024", "Different"],
        ],
    )

    assert fingerprint(left) == fingerprint(right)


def test_fingerprint_ignores_sheet_name_when_headers_match():
    left = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Purpose of meeting"]])
    right = NormalisedSheet(name="External meetings", rows=[["Minister", "Date", "Purpose of meeting"]])

    assert fingerprint(left) == fingerprint(right)


def test_fingerprint_changes_when_headers_change():
    left = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Purpose of meeting"]])
    right = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Organisation"]])

    assert fingerprint(left) != fingerprint(right)


def test_detect_header_row_prefers_real_gifts_header_over_short_data_rows():
    sheet = NormalisedSheet(
        name="default",
        rows=[
            ["Minister", "Gifts received over £140", "Gifts given over £140", "Date received/given", "From/To", "Value", "Outcome"],
            ["Attorney General Dominic Grieve QC MP", "Rug", "", "Jan-11", "General Abdul Rahim Wardak", "Over limit", "Retained by Department"],
            ["Attorney General Dominic Grieve QC MP", "Rug", "", "Jan-11", "President Karzai", "Over limit", "Purchased by Minister"],
        ],
    )

    assert detect_header_row(sheet) == 0


def test_detect_header_row_prefers_real_travel_header_over_day_range_rows():
    sheet = NormalisedSheet(
        name="default",
        rows=[
            [
                "Minister",
                "Date(s) of trip",
                "Destination",
                "Purpose of trip",
                "No 32 or RAF or Charter or Eurostar",
                "Number of officials accompanying Minister",
                "",
                "Total cost including travel",
            ],
            ["Attorney General Dominic Grieve QC MP", "", "", "", "", "", "", ""],
            ["", "25-27 October", "Marrakech, Morocco", "Arab Forum on Asset Recovery", "Charter", "", "", "£898.01"],
            ["", "10-16 November", "Falkland Islands", "Overseas Territories Conference of Attorneys General", "RAF", "", "", "£1,949"],
        ],
    )

    assert detect_header_row(sheet) == 0


def test_detect_header_row_prefers_compact_header_over_pathologically_wide_data_row():
    wide_data_row = [
        "Secretary of State for Business, Energy and Industrial Strategy, The Rt Hon Greg Clark MP",
        "2017-04-01 00:00:00",
        "Trades Union Congress",
        "To discuss industrial strategy",
    ]
    wide_data_row.extend(["Ben Wallace", "2016-01-10 00:00:00", "HMA Egypt", "Aviation Security"] * 200)
    sheet = NormalisedSheet(
        name="Meetings",
        rows=[
            ["Minister", "Date", "Name of organisation or individual", "Purpose of meeting"],
            wide_data_row,
        ],
    )

    assert detect_header_row(sheet) == 0


def test_detect_header_row_prefers_real_header_over_blank_subject_meeting_rows():
    sheet = NormalisedSheet(
        name="default",
        rows=[
            ["", "Date", "Name of organisation or individual", "Purpose of meeting"],
            ["", "", "", ""],
            ["Chris Skidmore MP, Parliamentary Secretary ( Minister for the Constitution)", "12-Jan", "Joseph Rowntree Foundation", "Movers and Renters roundtable"],
            ["", "24-Jan", "Elevations Network", "Student roundtable"],
            ["", "02-Feb", "The following London Local Authorities attended: Sutton", "London Local Authority Roundtable"],
        ],
    )

    assert detect_header_row(sheet) == 0


def test_long_narrative_meeting_values_do_not_count_as_header_labels():
    value = (
        "The following London Local Authorities attended: Sutton; Waltham Forest; Wandsworth; "
        "Hammersmith & Fulham; Brent; Camden; Haringey; Greenwich; Hounslow; Richmond"
    )

    assert looks_like_label(value) is False


def test_detect_header_row_rejects_late_long_text_meeting_rows():
    long_value = (
        "The following London Local Authorities attended: Sutton; Waltham Forest; Wandsworth; "
        "Hammersmith & Fulham; Brent; Camden; Haringey; Greenwich; Hounslow; Richmond; "
        "Ealing; Kensington & Chelsea; Lewisham; Tower Hamlets; Southwark"
    )
    sheet = NormalisedSheet(
        name="default",
        rows=[
            ["", "Date", "Name of organisation or individual", "Purpose of meeting"],
            ["", "", "", ""],
            ["Minister Name", "12-Jan", "Joseph Rowntree Foundation", "Movers and Renters roundtable"],
            ["", "24-Jan", "Elevations Network", "Student roundtable"],
            ["", "25-Jan", "Example Org", "Example purpose"],
            ["", "26-Jan", "Another Org", "Another purpose"],
            ["", "02-Feb", long_value, "London Local Authority Roundtable to hear their experiences to increase voter registration within their borough"],
        ],
    )

    assert detect_header_row(sheet) == 0
