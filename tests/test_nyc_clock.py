from datetime import datetime, timezone

import pytest

from scripts.nyc_clock import nyc_today_iso


def test_utc_midnight_does_not_advance_new_york_event_date():
    instant = datetime(2026, 7, 28, 0, 30, tzinfo=timezone.utc)
    assert nyc_today_iso(instant) == "2026-07-27"


def test_new_york_date_advances_after_local_midnight():
    instant = datetime(2026, 7, 28, 4, 30, tzinfo=timezone.utc)
    assert nyc_today_iso(instant) == "2026-07-28"


def test_winter_offset_is_respected():
    instant = datetime(2026, 1, 2, 3, 30, tzinfo=timezone.utc)
    assert nyc_today_iso(instant) == "2026-01-01"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        nyc_today_iso(datetime(2026, 7, 28, 0, 30))
