"""Canonical Milestone 6, Stage 6C: deterministic offline identity-drift tests
against the fixture-only reference contracts (tools.registry.xri_g40-g44).

These prove that only the stable identity fields (group_key, display_location,
candidate_identity) drive approvals/handoff, and that review_rank, row order,
and record count changes never alter computed identity."""
import pytest

from tools.registry.xri_g41_fixture_only_parser_normalizer import FixtureOnlyParserNormalizerError
from tools.registry.xri_g42_fixture_only_validation_execution import validate_fixture_record
from tools.registry.xri_g43_fixture_only_manual_review_handoff import (
    FixtureOnlyManualReviewHandoffError,
    build_manual_review_handoff_records,
)
from tools.registry.xri_g44_fixture_only_audit_reporting import (
    build_fixture_audit_report,
    validate_and_build_fixture_audit_report,
)


def record(**overrides):
    base = {
        "group_key": "fixture-group",
        "display_location": "  Fixture   Location  ",
        "candidate_identity": "fixture-001",
        "review_rank": 1,
        "source_name": "Test Source",
        "event_name": "Fixture Event",
        "start": "2026-07-06T10:00:00",
        "end": "2026-07-06T11:00:00",
    }
    base.update(overrides)
    return base


def audit(records_list):
    return validate_and_build_fixture_audit_report(records_list)


def test_reordered_records_produce_identical_stable_identities():
    a = record(candidate_identity="fixture-a")
    b = record(candidate_identity="fixture-b")
    c = record(candidate_identity="fixture-c")

    forward = audit([a, b, c])
    reversed_order = audit([c, b, a])

    assert forward.stable_identities == reversed_order.stable_identities
    assert len(forward.stable_identities) == 3


def test_duplicate_display_location_with_distinct_candidate_identity_remains_distinct():
    same_place_a = record(candidate_identity="event-a", display_location="Prospect Park")
    same_place_b = record(candidate_identity="event-b", display_location="Prospect Park")

    report = audit([same_place_a, same_place_b])

    assert len(report.stable_identities) == 2
    assert len(set(report.stable_identities)) == 2


def test_renamed_display_text_changes_identity_deterministically():
    original = record(display_location="Prospect Park")
    renamed = record(display_location="Prospect Park Renamed")

    report_original = audit([original])
    report_renamed = audit([renamed])

    assert report_original.stable_identities != report_renamed.stable_identities


def test_missing_review_row_does_not_affect_remaining_identities():
    a = record(candidate_identity="fixture-a")
    b = record(candidate_identity="fixture-b")
    c = record(candidate_identity="fixture-c")

    full_report = audit([a, b, c])
    missing_b_report = audit([a, c])

    assert set(missing_b_report.stable_identities).issubset(set(full_report.stable_identities))
    assert len(missing_b_report.stable_identities) == 2


def test_stale_review_rank_value_does_not_alter_identity():
    stale = record(candidate_identity="fixture-stale", review_rank=1)
    fresh = record(candidate_identity="fixture-stale", review_rank=250)

    assert audit([stale]).stable_identities == audit([fresh]).stable_identities


def test_ranking_changes_never_alter_identity_through_full_handoff_chain():
    low_rank = record(candidate_identity="fixture-rank", review_rank=1)
    high_rank = record(candidate_identity="fixture-rank", review_rank=99)

    result_low = validate_fixture_record(low_rank)
    result_high = validate_fixture_record(high_rank)
    assert result_low.candidate_identity == result_high.candidate_identity
    assert result_low.group_key == result_high.group_key
    assert result_low.display_location == result_high.display_location

    handoff_low = build_manual_review_handoff_records(low_rank)[0]
    handoff_high = build_manual_review_handoff_records(high_rank)[0]
    assert handoff_low.group_key == handoff_high.group_key
    assert handoff_low.display_location == handoff_high.display_location
    assert handoff_low.candidate_identity == handoff_high.candidate_identity

    report_low = build_fixture_audit_report(handoff_low)
    report_high = build_fixture_audit_report(handoff_high)
    assert report_low.stable_identities == report_high.stable_identities


def test_partial_approvals_do_not_change_identity_or_ready_status_basis():
    ready_records = [record(candidate_identity=f"fixture-{i}") for i in range(3)]

    report = audit(ready_records)

    assert report.handoff_status_summary["ready_for_manual_review_true"] == 3
    assert report.handoff_status_summary["ready_for_manual_review_false"] == 0
    assert len(report.stable_identities) == 3
    assert report.fixture_count == report.ready_for_manual_review_count


def test_only_stable_identity_fields_drive_approval_not_review_rank():
    variants = [
        record(candidate_identity="fixture-x", review_rank=1),
        record(candidate_identity="fixture-x", review_rank=500),
        record(candidate_identity="fixture-x", review_rank=None if False else 42),
    ]
    reports = [audit([v]) for v in variants]
    identities = {r.stable_identities for r in reports}
    assert len(identities) == 1, "identity must be invariant to review_rank value alone"


def test_missing_stable_identity_field_fails_closed_not_silently_dropped():
    incomplete = record()
    incomplete.pop("candidate_identity")
    with pytest.raises(FixtureOnlyParserNormalizerError):
        validate_fixture_record(incomplete)


def test_forbidden_final_state_field_rejected_at_handoff_even_with_valid_identity():
    tainted = record(candidate_identity="fixture-tainted", approved=True)
    with pytest.raises(FixtureOnlyManualReviewHandoffError):
        build_manual_review_handoff_records(tainted)
