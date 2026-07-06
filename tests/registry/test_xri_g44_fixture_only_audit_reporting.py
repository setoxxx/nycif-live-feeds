import pytest

from tools.registry.xri_g44_fixture_only_audit_reporting import (
    FixtureOnlyAuditReportingError,
    build_fixture_audit_report,
    validate_and_build_fixture_audit_report,
)


def payload():
    return {
        "group_key": "fixture-group",
        "display_location": "  Fixture   Location  ",
        "candidate_identity": "fixture-001",
        "review_rank": 1,
        "source_name": "  Test   Source ",
        "event_name": "  Fixture   Event ",
        "start": "2026-07-06T10:00:00",
        "end": "2026-07-06T11:00:00",
    }


def test_fixture_only_audit_reporting_pass():
    report = build_fixture_audit_report(payload())
    assert report.phase == "XRI-G44"
    assert report.fixture_count == 1
    assert report.ready_for_manual_review_count == 1


def test_accepts_list_and_single_fixture_input():
    assert build_fixture_audit_report(payload()).fixture_count == 1
    report = build_fixture_audit_report([payload(), {**payload(), "candidate_identity": "fixture-002"}])
    assert report.fixture_count == 2


def test_stable_identity_required():
    item = payload()
    item.pop("candidate_identity")
    with pytest.raises(Exception):
        build_fixture_audit_report(item)


def test_review_rank_is_not_identity():
    report = build_fixture_audit_report({**payload(), "review_rank": 99})
    assert report.stable_identities == ("fixture-group|Fixture Location|fixture-001",)
    assert "review_rank_identity_use" in report.raw_fixture_metadata_summary


def test_fixture_counts_are_deterministic():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    report = build_fixture_audit_report(items)
    assert report.fixture_count == 2
    assert report.ready_for_manual_review_count == 2


def test_stable_identity_list_deterministic():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    report = build_fixture_audit_report(items)
    assert report.stable_identities == (
        "fixture-group|Fixture Location|fixture-001",
        "fixture-group|Fixture Location|fixture-002",
    )


def test_validation_check_summary_deterministic():
    report = build_fixture_audit_report(payload())
    assert report.validation_check_summary["stable_identity_present"] == 1
    assert report.validation_check_summary["deterministic_fixture_only_validation"] == 1


def test_handoff_status_summary_deterministic():
    report = build_fixture_audit_report(payload())
    assert report.handoff_status_summary["ready_for_manual_review_true"] == 1
    assert report.handoff_status_summary["ready_for_manual_review_false"] == 0


@pytest.mark.parametrize("field", ["approval", "approved", "promotion", "promoted", "publishing", "published", "geocoded", "production_ready", "public_runtime_ready"])
def test_final_states_rejected(field):
    item = payload()
    item[field] = True
    with pytest.raises(Exception):
        build_fixture_audit_report(item)


def test_flagged_fixture_rejected():
    item = payload()
    item["production_target"] = True
    with pytest.raises(Exception):
        build_fixture_audit_report(item)


def test_deterministic_fixture_only_audit_reporting_output():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    assert validate_and_build_fixture_audit_report(items) == validate_and_build_fixture_audit_report(items)
