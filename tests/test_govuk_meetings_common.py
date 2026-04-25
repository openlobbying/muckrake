from datetime import datetime
from pathlib import Path

import pandas as pd

from datasets.gb.meetings.common import (
    Publication,
    Period,
    TableSource,
    canonical_records,
    detect_category,
    detect_gift_direction,
    detect_field_mapping,
    extract_publications,
    iter_publication_tables,
    make_resource_name,
    read_excel_tables,
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


class DummyResourceDataset:
    def __init__(self, path: Path):
        self.path = path

    def fetch_resource(self, name: str, url: str):
        return self.path


class DummyHtmlDataset:
    def __init__(self, pages):
        self.pages = pages

    def fetch_html(self, url: str, cache_days: int = 30, absolute_links: bool = True):
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page


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


def test_make_resource_name_shortens_long_publication_and_attachment_names():
    publication = Publication(
        url=(
            "https://www.gov.uk/government/publications/"
            "cabinet-office-ministerial-overseas-travel-and-meetings-october-to-december-2025"
        ),
        title="Example",
        period=None,
    )
    file_name = (
        "Rt_Hon_Sir_Keir_Starmer_KCB_KC_MP_-_Ministers__meetings_-_October_to_December_2025_"
        "-Rt_Hon_Sir_Keir_Starmer_KCB_KC_MP_-_Ministers__meetings_-_October_to_December_2025__1_.csv"
    )

    resource_name = make_resource_name(publication, file_name)

    assert resource_name.endswith(".csv")
    assert len(resource_name) < 160
    assert "cabinet-office-ministerial-overseas-travel-and-meetings" in resource_name


def test_read_excel_tables_falls_back_for_mislabeled_text_file(tmp_path):
    publication = Publication(
        url="https://www.gov.uk/government/publications/example",
        title="Example publication",
        period=None,
    )
    path = tmp_path / "example.xlsx"
    path.write_text("Minister,Date\nMinister Example,2024-01-10\n", encoding="utf-8")
    dataset = DummyResourceDataset(path)

    tables = list(read_excel_tables(dataset, publication, "example.xlsx", "https://assets.example.com/example.xlsx"))

    assert len(tables) == 1
    sheet_name, frame = tables[0]
    assert sheet_name == "example.xlsx"
    assert list(frame.columns) == ["minister", "date"]
    assert frame.iloc[0]["minister"] == "Minister Example"


def test_parse_range_dates_rejects_invalid_calendar_dates():
    from datasets.gb.meetings.common import parse_range_dates

    start_date, end_date = parse_range_dates("30-31 February 2016", None)

    assert start_date is None
    assert end_date is None


def test_read_csv_table_falls_back_for_irregular_legacy_rows(tmp_path):
    from datasets.gb.meetings.common import read_csv_table

    publication = Publication(
        url="https://www.gov.uk/government/publications/example",
        title="Example publication",
        period=None,
    )
    path = tmp_path / "example.csv"
    path.write_text(
        "Minister,Date of Hospitality,Name of Organisation,Type of hospitality received\n"
        "Secretary of State,11-Dec,Royal Opera House,Tickets\n"
        ",,,,,,,17\n",
        encoding="utf-8",
    )
    dataset = DummyResourceDataset(path)

    frame = read_csv_table(dataset, publication, "example.csv", "https://assets.example.com/example.csv")

    assert list(frame.columns) == [
        "minister",
        "date of hospitality",
        "name of organisation",
        "type of hospitality received",
    ]
    assert frame.iloc[0]["minister"] == "Secretary of State"


def test_extract_publications_skips_dead_collection_pages():
    from lxml import html

    dataset = DummyHtmlDataset(
        {
            "https://example.com/dead": RuntimeError("404"),
            "https://example.com/live": html.fromstring(
                '<a href="https://www.gov.uk/government/publications/example-publication">Example publication</a>'
            ),
        }
    )

    publications = extract_publications(
        dataset,
        ["https://example.com/dead", "https://example.com/live"],
    )

    assert len(publications) == 1
    assert publications[0].url == "https://www.gov.uk/government/publications/example-publication"


def test_iter_publication_tables_skips_dead_publication_pages():
    from lxml import html

    dataset = DummyHtmlDataset(
        {
            "https://example.com/collection": html.fromstring(
                '<a href="https://www.gov.uk/government/publications/example-publication">Example publication</a>'
            ),
            "https://www.gov.uk/government/publications/example-publication": RuntimeError("404"),
        }
    )

    tables = list(iter_publication_tables(dataset, ["https://example.com/collection"]))

    assert tables == []
