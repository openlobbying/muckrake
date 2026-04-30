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


def test_fingerprint_changes_when_headers_change():
    left = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Purpose of meeting"]])
    right = NormalisedSheet(name="Meetings", rows=[["Minister", "Date", "Organisation"]])

    assert fingerprint(left) != fingerprint(right)
