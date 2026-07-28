#!/usr/bin/env python3
"""Focused tests for strict source-occurrence reconciliation reason codes."""

from __future__ import annotations

from audit_strict_source_reconciliation import (
    classify_calendar_parks_row,
    classify_open_data_row,
)


def assert_equal(actual: str, expected: str) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def main() -> int:
    staged_occurrences = {("open-data", "1", "2026-07-20")}
    staged_sources = {("open-data", "1")}
    rejected_occurrences = {("open-data", "2", "2026-07-20")}
    rejected_sources = {("open-data", "2")}

    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "1", "date": "2026-07-20"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "represented_by_staged_occurrence",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "1", "date": "2026-07-21"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "in_window_occurrence_hidden_by_source_id_match",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "2", "date": "2026-07-20"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "rejected_with_documented_reason",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "3", "date": "2026-08-01"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "accepted_via_current_unstaged_season_intake",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "4", "date": "2027-01-10"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "excluded_outside_audited_season_window",
    )
    assert_equal(
        classify_open_data_row(
            {"source_dataset": "open-data", "source_event_id": "5"},
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_occurrences,
            rejected_source_keys=rejected_sources,
        ),
        "excluded_missing_or_unparseable_event_date",
    )

    accepted_supplemental_occurrences = {("calendar", "10", "2026-07-20")}
    all_supplemental_sources = {("calendar", "10"), ("parks", "11")}
    rejected_supplemental_sources = {("parks", "11")}
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "calendar", "source_event_id": "10", "date": "2026-07-20"},
            accepted_supplemental_occurrences=accepted_supplemental_occurrences,
            all_supplemental_source_keys=all_supplemental_sources,
            rejected_supplemental_source_keys=rejected_supplemental_sources,
        ),
        "represented_by_supplemental_occurrence",
    )
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "calendar", "source_event_id": "10", "date": "2026-07-21"},
            accepted_supplemental_occurrences=accepted_supplemental_occurrences,
            all_supplemental_source_keys=all_supplemental_sources,
            rejected_supplemental_source_keys=rejected_supplemental_sources,
        ),
        "occurrence_hidden_by_supplemental_source_id_match",
    )
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "parks", "source_event_id": "11", "date": "2026-07-20"},
            accepted_supplemental_occurrences=accepted_supplemental_occurrences,
            all_supplemental_source_keys=all_supplemental_sources,
            rejected_supplemental_source_keys=rejected_supplemental_sources,
        ),
        "rejected_by_manual_supplemental_review",
    )
    assert_equal(
        classify_calendar_parks_row(
            {"source_dataset": "parks", "source_event_id": "12", "date": "2026-07-20"},
            accepted_supplemental_occurrences=accepted_supplemental_occurrences,
            all_supplemental_source_keys=all_supplemental_sources,
            rejected_supplemental_source_keys=rejected_supplemental_sources,
        ),
        "accepted_via_current_unlinked_raw_intake",
    )
    print("strict source-occurrence reconciliation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
