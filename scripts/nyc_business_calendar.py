"""NYC business-day gate for official event snapshot refresh.

City Open Data / calendar cuts land on weekdays around 5–7pm ET.
Discovery must not treat Saturday, Sunday, or a city holiday as a new day.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")

# Observed NYC public holidays (city offices closed). Keep two years ahead.
FIXED_HOLIDAYS = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 12),
    date(2026, 2, 16),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),  # Independence Day observed
    date(2026, 9, 7),  # Labor Day
    date(2026, 10, 12),
    date(2026, 11, 3),  # Election Day
    date(2026, 11, 11),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 12),
    date(2027, 2, 15),
    date(2027, 5, 31),
    date(2027, 6, 18),  # Juneteenth observed
    date(2027, 7, 5),  # Independence Day observed
    date(2027, 9, 6),
    date(2027, 10, 11),
    date(2027, 11, 2),
    date(2027, 11, 11),
    date(2027, 11, 25),
    date(2027, 12, 24),  # Christmas observed
}


def today_nyc(now: datetime | None = None) -> date:
    current = now or datetime.now(NEW_YORK)
    if current.tzinfo is None:
        current = current.replace(tzinfo=NEW_YORK)
    return current.astimezone(NEW_YORK).date()


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def is_nyc_holiday(day: date) -> bool:
    return day in FIXED_HOLIDAYS


def is_nyc_business_day(day: date) -> bool:
    return not is_weekend(day) and not is_nyc_holiday(day)


def next_business_day(day: date) -> date:
    cursor = day + timedelta(days=1)
    while not is_nyc_business_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def refresh_decision(event_name: str, now: datetime | None = None) -> dict[str, str | bool]:
    """Scheduled jobs skip off days. workflow_dispatch always runs."""
    day = today_nyc(now)
    event = (event_name or "").strip() or "schedule"
    if event == "workflow_dispatch":
        return {
            "run": True,
            "reason": "manual_dispatch",
            "today_nyc": day.isoformat(),
            "business_day": is_nyc_business_day(day),
        }
    if is_weekend(day):
        return {
            "run": False,
            "reason": "weekend",
            "today_nyc": day.isoformat(),
            "business_day": False,
        }
    if is_nyc_holiday(day):
        return {
            "run": False,
            "reason": "nyc_holiday",
            "today_nyc": day.isoformat(),
            "business_day": False,
        }
    return {
        "run": True,
        "reason": "nyc_business_day",
        "today_nyc": day.isoformat(),
        "business_day": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", "schedule"))
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    decision = refresh_decision(args.event)
    line = (
        f"run={str(decision['run']).lower()} reason={decision['reason']} "
        f"today_nyc={decision['today_nyc']}"
    )
    print(line)
    if args.github_output:
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as handle:
                handle.write(f"run={'true' if decision['run'] else 'false'}\n")
                handle.write(f"reason={decision['reason']}\n")
                handle.write(f"today_nyc={decision['today_nyc']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
