"""Native map time-window contract: Now, Tonight after 6pm, next 7 days.

7 Days is an on/off control. When on, the phone shows Sat–Fri if today is
Friday: tomorrow through today+7, with weekday + date. Only events that
overlap that calendar day belong in that chip. Clicking 7 Days again returns
to Now.

Tonight is the same on/off control for today's events that start at or after
18:00 America/New_York. The locked Tonight auxiliary layers (5 PM Somewhere,
cannabis shops, liquor stores) stay overlays, not event rows.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TIMEZONE = "America/New_York"
NY_TZ = ZoneInfo(TIMEZONE)
TONIGHT_START_MINUTE = 18 * 60
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
NIGHT_AUX_LAYERS = (
    {
        "id": "5pm",
        "label": "It's 5 PM Somewhere",
        "emoji": "🍹",
        "layer": "5pm",
    },
    {
        "id": "dispensary",
        "label": "Legal Cannabis Shops",
        "emoji": "🌿",
        "layer": "dispensary",
    },
    {
        "id": "liquor",
        "label": "Liquor Stores",
        "emoji": "🍸",
        "layer": "liquor",
    },
)


def today_nyc(now: datetime | None = None) -> date:
    current = now or datetime.now(NY_TZ)
    return current.astimezone(NY_TZ).date()


def add_days(day: date, offset: int) -> date:
    return day + timedelta(days=offset)


def next_seven_days(today: date | None = None) -> list[dict[str, Any]]:
    """The next seven calendar days, starting tomorrow, not including today."""
    start = today or today_nyc()
    days: list[dict[str, Any]] = []
    for offset in range(1, 8):
        day = add_days(start, offset)
        weekday = WEEKDAYS[day.weekday()]
        days.append(
            {
                "date": day.isoformat(),
                "weekday": weekday,
                "weekday_short": weekday[:3],
                "label": f"{weekday} {day.strftime('%b')} {day.day}",
            }
        )
    return days


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY_TZ)
    return parsed.astimezone(NY_TZ)


def event_span(start_at: Any, end_at: Any) -> tuple[datetime, datetime] | None:
    start = parse_iso(start_at)
    if start is None:
        return None
    end = parse_iso(end_at) or (start + timedelta(hours=3))
    if end < start:
        end = start
    return start, end


def overlaps_calendar_day(start_at: Any, end_at: Any, day: date) -> bool:
    span = event_span(start_at, end_at)
    if span is None:
        return False
    start, end = span
    day_start = datetime(day.year, day.month, day.day, tzinfo=NY_TZ)
    day_end = day_start + timedelta(days=1)
    return start < day_end and end >= day_start


def overlaps_tonight(start_at: Any, end_at: Any, today: date | None = None) -> bool:
    day = today or today_nyc()
    if not overlaps_calendar_day(start_at, end_at, day):
        return False
    start = parse_iso(start_at)
    if start is None:
        return False
    return start.hour * 60 + start.minute >= TONIGHT_START_MINUTE


def overlaps_seven(start_at: Any, end_at: Any, today: date | None = None) -> bool:
    day = today or today_nyc()
    first = add_days(day, 1)
    last_exclusive = add_days(day, 8)
    span = event_span(start_at, end_at)
    if span is None:
        return False
    start, end = span
    window_start = datetime(first.year, first.month, first.day, tzinfo=NY_TZ)
    window_end = datetime(
        last_exclusive.year, last_exclusive.month, last_exclusive.day, tzinfo=NY_TZ
    )
    return start < window_end and end >= window_start


def normalize_mode(value: str | None) -> str:
    mode = str(value or "now").strip().lower()
    if mode in {"tonight"}:
        return "tonight"
    if mode in {"seven", "7d", "7day", "7days"}:
        return "seven"
    if mode in {"day"}:
        return "day"
    return "now"


def parse_day_param(value: str | None, today: date | None = None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    start = today or today_nyc()
    allowed = {add_days(start, offset) for offset in range(1, 8)}
    return parsed if parsed in allowed else None
