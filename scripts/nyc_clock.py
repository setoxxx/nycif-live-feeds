#!/usr/bin/env python3
"""Shared New York City clock helpers for event-date boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def nyc_today_iso(now: datetime | None = None) -> str:
    """Return the calendar date in New York for an aware instant."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("nyc_today_iso requires a timezone-aware datetime")
    return current.astimezone(NEW_YORK).date().isoformat()
