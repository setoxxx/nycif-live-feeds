"""Canonical Milestone 6, Stage 6F: deterministic offline tests for identity
persistence across pipeline-stage transitions, approval gating, and promotion
gating (defense-in-depth across xri_g40-g44)."""
import pytest

from tools.registry.xri_g42_fixture_only_validation_execution import validate_fixture_record
from tools.registry.xri_g43_fixture_only_manual_review_handoff import (
    ManualReviewHandoffRecord,
    build_manual_review_handoff_record,
    build_manual_review_handoff_records,
)
from tools.registry.xri_g44_fixture_only_audit_reporting import (
    FixtureOnlyAuditReportingError,
    build_fixture_audit_report,
    validate_and_build_fixture_audit_report,
)


def record(**overrides):
    base = {
        "group_key": "transition-group",
        "display_location": "Transition Location",
        "candidate_identity": "transition-001",
        "review_rank": 3,
        "source_name": "Transition Source",
        "event_name": "Transition Event",
        "start": "2026-08-01T09:00:00",
        "end": "2026-08-01T10:00:00",
    }
    base.update(overrides)
    return base


def test_identity_persists_unchanged_across_every_stage_transition():
    payload = record()

    validated = validate_fixture_record(payload)
    handoff = build_manual_review_handoff_record(validated)
    report = build_fixture_audit_report(handoff)

    assert validated.group_key == handoff.group_key == "transition-group"
    assert validated.display_location == handoff.display_location == "Transition Location"
    assert validated.candidate_identity == handoff.candidate_identity == "transition-001"
    assert report.stable_identities == ("transition-group|Transition Location|transition-001",)


def test_approval_gating_requires_ready_for_manual_review_true_after_validation():
    handoff = build_manual_review_handoff_record(record())
    assert handoff.ready_for_manual_review is True
    assert handoff.review_required_reason == "fixture_validated_requires_human_review"


def test_promotion_gating_is_enforced_redundantly_at_the_handoff_layer():
    with pytest.raises(Exception):
        build_manual_review_handoff_records(record(promoted=True))


def test_promotion_gating_is_enforced_redundantly_at_the_audit_report_layer():
    handoff = build_manual_review_handoff_record(record())
    tainted = ManualReviewHandoffRecord(
        group_key=handoff.group_key,
        display_location=handoff.display_location,
        candidate_identity=handoff.candidate_identity,
        ready_for_manual_review=handoff.ready_for_manual_review,
        review_required_reason=handoff.review_required_reason,
        normalized_summary=handoff.normalized_summary,
        validation_checks=handoff.validation_checks,
        raw_fixture_metadata={**handoff.raw_fixture_metadata, "promoted": True},
    )
    with pytest.raises(FixtureOnlyAuditReportingError):
        build_fixture_audit_report(tainted)


def test_pipeline_transition_preserves_distinct_identities_across_a_batch():
    batch = [record(candidate_identity=f"transition-{i:03d}") for i in range(5)]
    report = validate_and_build_fixture_audit_report(batch)

    assert report.fixture_count == 5
    assert len(set(report.stable_identities)) == 5
    assert report.ready_for_manual_review_count == 5


def test_pipeline_transition_deterministic_across_repeated_runs():
    batch = [record(candidate_identity=f"transition-{i:03d}") for i in range(4)]
    first = validate_and_build_fixture_audit_report(batch)
    second = validate_and_build_fixture_audit_report(batch)
    assert first == second
