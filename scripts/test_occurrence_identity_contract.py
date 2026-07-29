#!/usr/bin/env python3
"""Focused tests for dated-occurrence identity enforcement."""

from __future__ import annotations

from occurrence_identity_contract import (
    classify_open_data_occurrence,
    occurrence_key,
    source_id_only_matching_allowed_for_recurring_event_feeds,
    source_key,
)

SEASON_START = "2026-07-14"
SEASON_END = "2026-12-27"


def main() -> int:
    staged = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "date": "2026-07-20",
    }
    same_date = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "date": "2026-07-20",
    }
    different_date = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "date": "2026-07-21",
    }
    outside_window = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "date": "2027-01-05",
    }
    rejected = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "reject-me",
        "date": "2026-07-22",
    }

    staged_sources = {source_key(staged)}
    staged_occurrences = {occurrence_key(staged)}
    rejected_sources = {source_key(rejected)}
    rejected_occurrences = {occurrence_key(rejected)}

    assert source_key(staged) == ("tvpp-9vvx", "abc123")
    assert occurrence_key(staged) == ("tvpp-9vvx", "abc123", "2026-07-20")
    assert source_id_only_matching_allowed_for_recurring_event_feeds() is False

    assert classify_open_data_occurrence(
        same_date,
        staged_source_keys=staged_sources,
        staged_occurrence_keys=staged_occurrences,
        rejected_source_keys=rejected_sources,
        rejected_occurrence_keys=rejected_occurrences,
        season_start=SEASON_START,
        season_end=SEASON_END,
        matching_mode="dated_occurrence",
    ) == "represented_by_staged_occurrence"

    assert classify_open_data_occurrence(
        different_date,
        staged_source_keys=staged_sources,
        staged_occurrence_keys=staged_occurrences,
        rejected_source_keys=rejected_sources,
        rejected_occurrence_keys=rejected_occurrences,
        season_start=SEASON_START,
        season_end=SEASON_END,
        matching_mode="source_id_only",
    ) == "in_window_occurrence_hidden_by_source_id_match"

    assert classify_open_data_occurrence(
        different_date,
        staged_source_keys=staged_sources,
        staged_occurrence_keys=staged_occurrences,
        rejected_source_keys=rejected_sources,
        rejected_occurrence_keys=rejected_occurrences,
        season_start=SEASON_START,
        season_end=SEASON_END,
        matching_mode="dated_occurrence",
    ) == "accepted_via_occurrence_keyed_unstaged_intake"

    assert classify_open_data_occurrence(
        outside_window,
        staged_source_keys=staged_sources,
        staged_occurrence_keys=staged_occurrences,
        rejected_source_keys=set(),
        rejected_occurrence_keys=set(),
        season_start=SEASON_START,
        season_end=SEASON_END,
        matching_mode="dated_occurrence",
    ) == "excluded_outside_audited_season_window"

    assert classify_open_data_occurrence(
        rejected,
        staged_source_keys=staged_sources,
        staged_occurrence_keys=staged_occurrences,
        rejected_source_keys=rejected_sources,
        rejected_occurrence_keys=rejected_occurrences,
        season_start=SEASON_START,
        season_end=SEASON_END,
        matching_mode="dated_occurrence",
    ) == "rejected_with_documented_reason"

    print("occurrence identity contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
