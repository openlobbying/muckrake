from pathlib import Path
import importlib.util
import sys


MODULE_PATH = Path("datasets/gb/gov-transparency/normalise.py")
SPEC = importlib.util.spec_from_file_location("gov_transparency_normalise", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NormalisedSheet = MODULE.NormalisedSheet
detect_file_format = MODULE.detect_file_format
normalise = MODULE.normalise

RESOURCE_ROOT = Path("data/datasets/gb_gov_transparency/resources")


def load_fixture(relative_path: str) -> bytes:
    return (RESOURCE_ROOT / relative_path).read_bytes()


def assert_non_empty_sheets(sheets: list[NormalisedSheet]):
    assert sheets
    assert all(isinstance(sheet.name, str) and sheet.name for sheet in sheets)
    assert all(isinstance(sheet.rows, list) for sheet in sheets)
    assert any(sheet.rows for sheet in sheets)
    for sheet in sheets:
        for row in sheet.rows[:10]:
            assert all(isinstance(cell, str) for cell in row)


def test_normalise_csv_fixture():
    relative_path = (
        "cabinet-office-ministerial-gifts-hospitality-travel-and-meetings-july-to-september-2016/"
        "Cabinet_Office_Ministerial__hospitality_July_-_September.csv"
    )
    data = load_fixture(relative_path)

    sheets = normalise(data, relative_path)

    assert len(sheets) == 1
    assert sheets[0].name == "default"
    assert_non_empty_sheets(sheets)


def test_normalise_html_tables_use_headings_as_sheet_names():
    data = b"""
    <html>
      <body>
        <h2>Meetings</h2>
        <table>
          <tr><th>Date</th><th>Organisation</th></tr>
          <tr><td>2025-01-01</td><td>Example Org</td></tr>
        </table>
        <h3>Outside employment</h3>
        <table>
          <tr><th>Name</th><th>Role</th></tr>
          <tr><td>Jane Doe</td><td>Board member</td></tr>
        </table>
      </body>
    </html>
    """

    sheets = normalise(data, "publication.html")

    assert [sheet.name for sheet in sheets] == ["Meetings", "Outside employment"]
    assert sheets[0].rows[0] == ["Date", "Organisation"]
    assert sheets[1].rows[1] == ["Jane Doe", "Board member"]


def test_normalise_csv_replaces_invalid_bytes():
    sheets = normalise(b"name,value\nAlice,\xff\n", "bad.csv")

    assert sheets[0].rows == [["name", "value"], ["Alice", "ÿ"]]


def test_detect_file_format_detects_html_from_magic_bytes():
    assert detect_file_format(b"\n\n<!doctype html><html></html>", "wrong-name.csv") == "html"


def test_normalise_xls_fixture():
    relative_path = (
        "cabinet-office-special-advisers-gifts-hospitality-and-meetings-april-june-2016/"
        "Special_Adviser_Gifts_and_Hospitality_Apr-Jun_2016__004___Updated_.xls"
    )
    data = load_fixture(relative_path)

    sheets = normalise(data, relative_path)

    assert_non_empty_sheets(sheets)
    assert {sheet.name for sheet in sheets} >= {"Notes", "Gifts", "Hospitality", "Meetings"}


def test_normalise_xlsx_fixture():
    relative_path = (
        "cabinet-office-special-advisers-gifts-hospitality-and-meetings-october-to-december-2015/"
        "CO_Special_Adviser_Oct_-_Dec_2015_xls.xlsx"
    )
    data = load_fixture(relative_path)

    sheets = normalise(data, relative_path)

    assert_non_empty_sheets(sheets)
    assert {sheet.name for sheet in sheets} >= {"Notes", "Gifts", "Hospitality", "Meetings"}


def test_normalise_xlsm_fixture():
    relative_path = (
        "beis-special-advisers-gifts-hospitality-and-meetings-october-to-december-2016/"
        "october_december_2016_bis_publications_special_adviser_final.xlsm"
    )
    data = load_fixture(relative_path)

    sheets = normalise(data, relative_path)

    assert_non_empty_sheets(sheets)
    assert {sheet.name for sheet in sheets} >= {"Notes", "Gifts", "Hospitality", "Meetings"}


def test_normalise_ods_fixture():
    relative_path = (
        "cabinet-office-ministerial-gifts-hospitality-travel-and-meetings-july-to-september-2016/"
        "prime_minister_quarterly_returns_july_to_september_2016.ods"
    )
    data = load_fixture(relative_path)

    sheets = normalise(data, relative_path)

    assert_non_empty_sheets(sheets)
    assert {sheet.name for sheet in sheets} >= {
        "Gifts",
        "Hospitality",
        "Overseas_travel",
        "Meetings",
    }


def test_normalise_skips_pdf_fixture():
    relative_path = (
        "bis-special-advisers-gifts-hospitality-and-meetings-october-to-december-2013/"
        "October_December2013_bis_quarterly_publications_spads_final.pdf"
    )
    data = load_fixture(relative_path)

    assert normalise(data, relative_path) == []


def test_normalise_skips_docx_fixture():
    relative_path = (
        "dcms-special-advisers-quarterly-return-on-gifts-and-hospitality-1-january-31-march-2013/"
        "Jan_14_to_March_14_SpAds_docx.docx"
    )
    data = load_fixture(relative_path)

    assert normalise(data, relative_path) == []


def test_detect_file_format_prefers_magic_bytes_over_wrong_extension():
    relative_path = (
        "cabinet-office-ministerial-gifts-hospitality-travel-and-meetings-july-to-september-2016/"
        "Cabinet_Office_Ministerial__hospitality_July_-_September.csv"
    )
    data = load_fixture(relative_path)

    assert detect_file_format(data, "wrong-name.xls") == "csv"
