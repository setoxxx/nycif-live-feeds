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


def test_calendar_occurrence_identity_includes_date() -> None:
    base = {
        "source_dataset": "nyc-citywide-events-calendar-api",
        "source_event_id": "abc",
        "title": "Recurring workshop",
    }
    first = {**base, "start_date_time": "2026-08-01T10:00:00"}
    second = {**base, "start_date_time": "2026-08-08T10:00:00"}
    assert occurrence_key(first) != occurrence_key(second)


def main() -> int:
    tests = [
        test_recurring_dates_are_preserved,
        test_exact_occurrence_duplicate_is_suppressed,
        test_calendar_occurrence_identity_includes_date,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
