from datetime import datetime

import pandas as pd

from datasets.gb.meetings.common import (
    Publication,
    Period,
    TableSource,
    canonical_records,
    detect_category,
    detect_gift_direction,
    detect_field_mapping,
    normalize_excel_sheet,
    normalize_tabular_frame,
)


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


def test_detect_category_prefers_specific_sheet_name_over_ambiguous_url():
    category = detect_category(
        "Meetings",
        "hmt-ministers-meetings-hospitality-gifts-and-overseas-travel.xlsx",
        "https://assets.publishing.service.gov.uk/media/hmt-ministers-meetings-hospitality-gifts-and-overseas-travel.xlsx",
    )
    assert category == "meetings"


def test_detect_field_mapping_uses_blank_first_column_for_meeting_minister():
    columns = [
        "unnamed 0",
        "date",
        "name of organisation",
        "purpose of meeting",
    ]
    field_map = detect_field_mapping("meetings", columns)
    assert field_map["minister"] == "unnamed 0"
    assert field_map["date"] == "date"
    assert field_map["counterparty"] == "name of organisation"


def test_detect_field_mapping_remaps_name_to_minister_when_specific_counterparty_exists():
    columns = [
        "name",
        "meeting date",
        "name of organisation or individual",
        "details",
    ]
    field_map = detect_field_mapping("meetings", columns)
    assert field_map["minister"] == "name"
    assert field_map["counterparty"] == "name of organisation or individual"
    assert field_map["purpose"] == "details"


def test_canonical_records_forward_fill_blank_first_column_minister():
    frame = pd.DataFrame(
        [
            {
                "unnamed 0": "The Rt Hon George Osborne MP",
                "date": "May",
                "name of organisation": "Mayor Of London",
                "purpose of meeting": "To discuss the London economy",
            },
            {
                "unnamed 0": None,
                "date": "May",
                "name of organisation": "Manchester City Council",
                "purpose of meeting": "To discuss the Northern Powerhouse",
            },
        ]
    )
    source = make_source("meetings", frame)
    records = list(canonical_records(source))
    assert records[0]["minister"] == "The Rt Hon George Osborne MP"
    assert records[1]["minister"] == "The Rt Hon George Osborne MP"


def test_normalize_excel_sheet_detects_header_row_below_title_rows():
    frame = pd.DataFrame(
        [
            ["HM Treasury ministers' meetings", None, None, None],
            ["January to March 2024", None, None, None],
            ["Minister", "Date", "Name of Individual or Organisation", "Purpose of Meeting"],
            ["Jeremy Hunt", "2024-01-04", "Openreach", "To discuss skills"],
        ]
    )
    normalized = normalize_excel_sheet(frame)
    assert list(normalized.columns) == [
        "minister",
        "date",
        "name of individual or organisation",
        "purpose of meeting",
    ]
    assert normalized.iloc[0]["minister"] == "Jeremy Hunt"
    assert normalized.iloc[0]["name of individual or organisation"] == "Openreach"


def test_normalize_tabular_frame_handles_old_meetings_csv_layout():
    frame = pd.DataFrame(
        [
            ["MEETINGS WITH EXTERNAL ORGANISATIONS", None, None],
            ["Secretary of State for Transport - The Rt Hon Patrick McLoughlin MP", None, None],
            ["Date of Meeting", "Name of External Organisation", "Purpose of Meeting"],
            ["Jan", "Centro", "Local priorities"],
        ]
    )
    normalized = normalize_tabular_frame(frame)
    assert list(normalized.columns) == [
        "date of meeting",
        "name of external organisation",
        "purpose of meeting",
    ]
    assert normalized.iloc[0]["name of external organisation"] == "Centro"


def test_canonical_records_capture_minister_from_section_header_rows():
    frame = pd.DataFrame(
        [
            {
                "date of meeting": "Secretary of State for Transport - The Rt Hon Patrick McLoughlin MP",
                "name of external organisation": None,
                "purpose of meeting": None,
            },
            {
                "date of meeting": "Jan",
                "name of external organisation": "Centro",
                "purpose of meeting": "Local priorities",
            },
        ]
    )
    source = make_source("meetings", frame)
    records = list(canonical_records(source))
    assert len(records) == 1
    assert records[0]["minister"] == "The Rt Hon Patrick McLoughlin MP"
    assert records[0]["counterparty"] == "Centro"


def test_canonical_records_inherit_date_and_purpose_for_dash_rows():
    frame = pd.DataFrame(
        [
            {
                "minister": "The Rt Hon Patrick McLoughlin MP",
                "date": "Feb",
                "name of external organisation": "Confederation of Passenger Transport:",
                "purpose of meeting": "Bus Discussion",
            },
            {
                "minister": None,
                "date": None,
                "name of external organisation": "-Arriva",
                "purpose of meeting": None,
            },
        ]
    )
    source = make_source("meetings", frame)
    records = list(canonical_records(source))
    assert records[1]["minister"] == "The Rt Hon Patrick McLoughlin MP"
    assert records[1]["date"] == "Feb"
    assert records[1]["purpose"] == "Bus Discussion"
    assert records[1]["counterparty"] == "Arriva"


def test_detect_gift_direction_from_old_split_files():
    assert detect_gift_direction("DfT ministerial gifts given, January to March 2015") == "Given"
    assert detect_gift_direction("DfT ministerial gifts received, January to March 2015") == "Received"


def test_canonical_records_infer_direction_for_split_gift_files():
    frame = pd.DataFrame(
        [
            {
                "minister": "Minister Example",
                "date gift received": "05/01/2015",
                "from": "Example Corp",
                "gift": "Bottle",
                "value": "150",
                "outcome": "Held by department",
            }
        ]
    )
    source = TableSource(
        publication=Publication(
            url="https://www.gov.uk/government/publications/example",
            title="January to March 2015 example",
            period=Period(start=datetime(2015, 1, 1).date(), end=datetime(2015, 3, 31).date()),
        ),
        category="gifts",
        source_url="https://assets.publishing.service.gov.uk/example-gifts-received.csv",
        title="DfT ministerial gifts received, January to March 2015",
        file_name="dft-gifts-received.csv",
        frame=frame,
    )
    records = list(canonical_records(source))
    assert records[0]["direction"] == "Received"
    assert records[0]["counterparty"] == "Example Corp"
