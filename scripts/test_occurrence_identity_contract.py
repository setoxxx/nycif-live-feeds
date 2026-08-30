#!/usr/bin/env python3
"""Focused tests for occurrence identity enforcement."""

from __future__ import annotations

from occurrence_identity_contract import (
    REJECTION_SCOPE_EXACT_START,
    REJECTION_SCOPE_SOURCE_ALL,
    classify_open_data_occurrence,
    identity_precision,
    occurrence_key,
    occurrence_key_v2,
    rejection_identity_sets,
    rejection_matches,
    source_id_only_matching_allowed_for_recurring_event_feeds,
    source_key,
)

SEASON_START = "2026-07-14"
SEASON_END = "2026-12-27"


def main() -> int:
    staged = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "start_date_time": "2026-07-20T09:00:00",
    }
    same_date = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "start_date_time": "2026-07-20T09:00:00",
    }
    same_day_different_time = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "start_date_time": "2026-07-20T14:00:00",
    }
    different_date = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "start_date_time": "2026-07-21T09:00:00",
    }
    date_only = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "day-only",
        "date": "2026-07-22",
    }
    missing_time_and_date = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "ambiguous",
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

    canonical_form = {
        "id": "canonical-hash-do-not-use-as-native-source-id",
        "source": {"dataset": "tvpp-9vvx", "source_event_id": "abc123"},
        "start_date_time": "2026-07-20T09:00:00",
    }
    legacy_id_only = {"dataset": "legacy-source", "id": "legacy-id"}

    staged_sources = {source_key(staged)}
    staged_occurrences = {occurrence_key(staged)}
    rejected_sources = {source_key(rejected)}
    rejected_occurrences = {occurrence_key(rejected)}

    assert source_key(staged) == ("tvpp-9vvx", "abc123")
    assert source_key(canonical_form) == ("tvpp-9vvx", "abc123")
    assert source_key(legacy_id_only) == ("legacy-source", "legacy-id")
    assert occurrence_key_v2(canonical_form) == occurrence_key_v2(staged)
    assert occurrence_key(staged) == ("tvpp-9vvx", "abc123", "2026-07-20")
    assert occurrence_key_v2(staged) == ("tvpp-9vvx", "abc123", "2026-07-20T09:00:00")
    assert occurrence_key_v2(same_day_different_time) == (
        "tvpp-9vvx",
        "abc123",
        "2026-07-20T14:00:00",
    )
    assert occurrence_key_v2(staged) != occurrence_key_v2(same_day_different_time)
    assert identity_precision(staged) == "EXACT_START"
    assert identity_precision(date_only) == "DAY"
    assert identity_precision(missing_time_and_date) == "AMBIGUOUS"
    assert source_id_only_matching_allowed_for_recurring_event_feeds() is False

    recurring_days = [
        {
            "dataset": "nycif-feast",
            "source_event_id": "18th-ave-feast-2026",
            "start_date_time": f"2026-08-{day:02d}T12:00:00",
        }
        for day in (29, 30, 31)
    ]
    assert len({occurrence_key_v2(row) for row in recurring_days}) == 3

    # Exact-start rejection must not widen to a sibling occurrence on the same day.
    exact_rejection = {
        **same_date,
        "manual_review_status": "rejected",
        "rejection_scope": REJECTION_SCOPE_EXACT_START,
    }
    exact, days, sources = rejection_identity_sets([exact_rejection])
    assert rejection_matches(
        same_date,
        rejected_exact=exact,
        rejected_days=days,
        rejected_sources=sources,
    ) is True
    assert rejection_matches(
        same_day_different_time,
        rejected_exact=exact,
        rejected_days=days,
        rejected_sources=sources,
    ) is False

    # Source-wide rejection is allowed only when explicitly declared.
    source_wide_rejection = {
        "dataset": "tvpp-9vvx",
        "source_event_id": "abc123",
        "manual_review_status": "rejected",
        "rejection_scope": REJECTION_SCOPE_SOURCE_ALL,
    }
    exact, days, sources = rejection_identity_sets([source_wide_rejection])
    assert rejection_matches(
        same_date,
        rejected_exact=exact,
        rejected_days=days,
        rejected_sources=sources,
    ) is True
    assert rejection_matches(
        different_date,
        rejected_exact=exact,
        rejected_days=days,
        rejected_sources=sources,
    ) is True

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
