#!/usr/bin/env python3
"""Deterministic regressions for the daily production hardening path."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.build_staged_production_feed import apply_one_day_street_dedupe  # noqa: E402
from scripts.refresh_official_supplemental_occurrences import occurrence_key  # noqa: E402
from scripts.sync_nyc_citywide_events_calendar import bool_flag  # noqa: E402


def street_row(day: str, source_event_id: str, *, priority: int = 0) -> dict:
    return {
        "id": f"tvpp-9vvx:{source_event_id}@{day}",
        "title": "Neighborhood Open Street",
        "event_name": "Neighborhood Open Street",
        "event_type": "Street Event",
        "borough": "Brooklyn",
        "display_location": "MAIN STREET between FIRST AVENUE and SECOND AVENUE",
        "lat": 40.65,
        "lng": -73.95,
        "date": day,
        "start_date_time": f"{day}T10:00:00.000",
        "end_date_time": f"{day}T18:00:00.000",
        "source_dataset": "tvpp-9vvx",
        "source_event_id": source_event_id,
        "source_cemsid": ["CEMS-123"],
        "priority_score": priority,
        "needs_review": False,
    }


def test_recurring_dates_are_preserved() -> None:
    first = street_row("2026-08-01", "1001")
    second = street_row("2026-08-08", "1002")
    kept, rejected = apply_one_day_street_dedupe([first, second])
    assert len(kept) == 2, kept
    assert rejected == [], rejected


def test_exact_occurrence_duplicate_is_suppressed() -> None:
    first = street_row("2026-08-01", "1001", priority=1)
    duplicate = copy.deepcopy(first)
    duplicate["source_event_id"] = "1001-copy"
    duplicate["id"] = "tvpp-9vvx:1001-copy@2026-08-01"
    duplicate["priority_score"] = 9
    kept, rejected = apply_one_day_street_dedupe([first, duplicate])
    assert len(kept) == 1, kept
    assert len(rejected) == 1, rejected
    assert kept[0]["source_event_id"] == "1001-copy", kept


def calendar_base() -> dict:
    return {
        "source_dataset": "nyc-citywide-events-calendar-api",
        "source_event_id": "abc",
        "title": "Recurring workshop",
    }


def test_calendar_occurrence_identity_includes_date() -> None:
    first = {**calendar_base(), "start_date_time": "2026-08-01T10:00:00"}
    second = {**calendar_base(), "start_date_time": "2026-08-08T10:00:00"}
    assert occurrence_key(first) != occurrence_key(second)


def test_calendar_occurrence_identity_includes_same_day_time() -> None:
    morning = {**calendar_base(), "start_date_time": "2026-08-01T10:00:00"}
    afternoon = {**calendar_base(), "start_date_time": "2026-08-01T14:00:00"}
    assert occurrence_key(morning) != occurrence_key(afternoon)


def test_calendar_cancellation_flags_are_typed_safely() -> None:
    assert bool_flag(True) is True
    assert bool_flag("true") is True
    assert bool_flag("1") is True
    assert bool_flag(False) is False
    assert bool_flag("false") is False
    assert bool_flag("0") is False
    assert bool_flag(None) is False


def main() -> int:
    tests = [
        test_recurring_dates_are_preserved,
        test_exact_occurrence_duplicate_is_suppressed,
        test_calendar_occurrence_identity_includes_date,
        test_calendar_occurrence_identity_includes_same_day_time,
        test_calendar_cancellation_flags_are_typed_safely,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
