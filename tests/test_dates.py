from datetime import date

from muckrake.utils.dates import parse_day_range


def test_cross_month_range_with_underscore_and_omitted_start_year():
    # The exact cell that killed a 14.6h gov_transparency crawl
    # (openlobbying/openlobbying#29).
    assert parse_day_range("27 Sep _ 01 Oct 15") == ("2015-09-27", "2015-10-01")


def test_cross_month_range_with_both_years():
    assert parse_day_range("27 Sep 15-01 Oct 15") == ("2015-09-27", "2015-10-01")
    assert parse_day_range("27 Sep 2015 - 1 Oct 2015") == ("2015-09-27", "2015-10-01")


def test_cross_month_range_omitted_start_year_infers_from_end():
    assert parse_day_range("30 Dec _ 02 Jan 16") == ("2015-12-30", "2016-01-02")


def test_same_month_range_with_underscore_separator():
    assert parse_day_range("8_12 July 2015") == ("2015-07-08", "2015-07-12")


def test_same_month_range_still_parses():
    assert parse_day_range("8-12 July 2015") == ("2015-07-08", "2015-07-12")
    assert parse_day_range("8 to 12 July 2015") == ("2015-07-08", "2015-07-12")
    assert parse_day_range(
        "8-12 July", start=date(2015, 4, 1), end=date(2015, 9, 30)
    ) == ("2015-07-08", "2015-07-12")


def test_slash_day_pair_range_still_parses():
    assert parse_day_range("8/9 July 2015") == ("2015-07-08", "2015-07-09")


def test_numeric_range_still_parses():
    assert parse_day_range("08/07/2015-09/07/2015") == ("2015-07-08", "2015-07-09")


def test_garbage_returns_none():
    assert parse_day_range("not a date") is None
    assert parse_day_range("27 Sep _ 01 Vember 15") is None
