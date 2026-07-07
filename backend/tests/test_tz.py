from datetime import date, datetime, timezone

from app.services.tz import day_window


def test_summer_day_new_york():
    start, end = day_window(date(2026, 7, 7), "America/New_York")
    assert start == datetime(2026, 7, 7, 4, 0, tzinfo=timezone.utc)  # EDT = UTC-4
    assert end == datetime(2026, 7, 8, 4, 0, tzinfo=timezone.utc)


def test_dst_end_day_is_25_hours():
    # DST ends Nov 1 2026 in the US — that local day really is 25 hours.
    start, end = day_window(date(2026, 11, 1), "America/New_York")
    assert (end - start).total_seconds() == 25 * 3600


def test_dst_start_day_is_23_hours():
    start, end = day_window(date(2026, 3, 8), "America/New_York")
    assert (end - start).total_seconds() == 23 * 3600


def test_utc_family():
    start, end = day_window(date(2026, 7, 7), "UTC")
    assert start == datetime(2026, 7, 7, tzinfo=timezone.utc)
    assert (end - start).total_seconds() == 24 * 3600
