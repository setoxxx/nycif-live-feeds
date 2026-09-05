from datetime import date, datetime

from scripts.nyc_business_calendar import (
    is_nyc_business_day,
    next_business_day,
    refresh_decision,
    today_nyc,
)
from scripts.nyc_clock import NEW_YORK


def test_saturday_is_not_a_business_day() -> None:
    assert is_nyc_business_day(date(2026, 9, 5)) is False


def test_labor_day_2026_is_not_a_business_day() -> None:
    assert is_nyc_business_day(date(2026, 9, 7)) is False


def test_tuesday_after_labor_day_is_open() -> None:
    assert is_nyc_business_day(date(2026, 9, 8)) is True


def test_next_business_day_skips_weekend_and_labor_day() -> None:
    assert next_business_day(date(2026, 9, 4)) == date(2026, 9, 8)


def test_scheduled_refresh_skips_saturday() -> None:
    now = datetime(2026, 9, 5, 19, 0, tzinfo=NEW_YORK)
    decision = refresh_decision("schedule", now=now)
    assert decision["run"] is False
    assert decision["reason"] == "weekend"


def test_manual_dispatch_runs_on_saturday() -> None:
    now = datetime(2026, 9, 5, 11, 0, tzinfo=NEW_YORK)
    decision = refresh_decision("workflow_dispatch", now=now)
    assert decision["run"] is True
    assert decision["reason"] == "manual_dispatch"


def test_today_nyc_uses_new_york() -> None:
    now = datetime(2026, 9, 5, 1, 0, tzinfo=NEW_YORK)
    assert today_nyc(now) == date(2026, 9, 5)
