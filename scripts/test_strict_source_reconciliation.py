#!/usr/bin/env python3
"""Focused unit tests for strict source reconciliation reason codes."""

from __future__ import annotations

from audit_strict_source_reconciliation import (
    classify_calendar_parks_row,
    classify_open_data_row,
)


def assert_equal(actual: str, expected: str) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def main() -> int:
    staged = {("open-data", "1")}
    rejected = {("open-data", "2")}

    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "1", "date": "2026-07-20"},
            staged_keys=staged,
            rejected_keys=rejected,
        ),
        "accepted_via_staged_feed",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "2", "date": "2026-07-20"},
            staged_keys=staged,
            rejected_keys=rejected,
        ),
        "rejected_with_documented_reason",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "3", "date": "2026-08-01"},
            staged_keys=staged,
            rejected_keys=rejected,
        ),
        "accepted_via_unstaged_season_intake",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "4", "date": "2027-01-10"},
            staged_keys=staged,
            rejected_keys=rejected,
        ),
        "excluded_outside_audited_season_window",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "5"},
            staged_keys=staged,
            rejected_keys=rejected,
        ),
        "excluded_missing_or_unparseable_event_date",
    )

    accepted_supplemental = {("calendar", "10")}
    rejected_supplemental = {("parks", "11")}
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "calendar", "source_event_id": "10"},
            accepted_supplemental_keys=accepted_supplemental,
            rejected_supplemental_keys_set=rejected_supplemental,
        ),
        "accepted_via_supplemental_staging",
    )
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "parks", "source_event_id": "11"},
            accepted_supplemental_keys=accepted_supplemental,
            rejected_supplemental_keys_set=rejected_supplemental,
        ),
        "rejected_by_manual_supplemental_review",
    )
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "parks", "source_event_id": "12"},
            accepted_supplemental_keys=accepted_supplemental,
            rejected_supplemental_keys_set=rejected_supplemental,
        ),
        "accepted_via_unlinked_raw_intake",
    )
    print("strict source reconciliation unit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
