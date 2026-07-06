import pytest

from tools.registry.xri_g43_fixture_only_manual_review_handoff import (
    FixtureOnlyManualReviewHandoffError,
    build_manual_review_handoff_record,
    build_manual_review_handoff_records,
    validate_and_build_manual_review_handoff_records,
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


def test_fixture_only_manual_review_handoff_pass():
    result = build_manual_review_handoff_record(payload())
    assert result.ready_for_manual_review is True
    assert result.group_key == "fixture-group"
    assert result.display_location == "Fixture Location"


def test_accepts_list_and_single_fixture_input():
    assert len(build_manual_review_handoff_records(payload())) == 1
    assert len(build_manual_review_handoff_records([payload(), {**payload(), "candidate_identity": "fixture-002"}])) == 2


def test_stable_identity_required():
    item = payload()
    item.pop("candidate_identity")
    with pytest.raises(Exception):
        build_manual_review_handoff_record(item)


def test_review_rank_is_not_identity():
    result = build_manual_review_handoff_record({**payload(), "review_rank": 99})
    assert result.candidate_identity == "fixture-001"
    assert result.raw_fixture_metadata["review_rank_identity_use"] == "forbidden_display_only"


def test_ready_for_manual_review_true_for_valid_fixture_only():
    result = build_manual_review_handoff_record(payload())
    assert result.ready_for_manual_review is True
    assert result.review_required_reason == "fixture_validated_requires_human_review"


@pytest.mark.parametrize("field", ["approval", "approved", "promotion", "promoted", "publishing", "published", "geocoded", "production_ready", "public_runtime_ready"])
def test_final_states_rejected(field):
    item = payload()
    item[field] = True
    with pytest.raises(FixtureOnlyManualReviewHandoffError):
        build_manual_review_handoff_record(item)


def test_normalized_summary_produced_deterministically():
    result = build_manual_review_handoff_record(payload())
    assert result.normalized_summary["source_name"] == "Test Source"
    assert result.normalized_summary["event_name"] == "Fixture Event"
    assert result.normalized_summary["start"] == "2026-07-06T10:00:00"


def test_validation_checks_carried_forward_deterministically():
    result = build_manual_review_handoff_record(payload())
    assert "stable_identity_present" in result.validation_checks
    assert "deterministic_fixture_only_validation" in result.validation_checks


def test_flagged_fixture_rejected():
    item = payload()
    item["production_target"] = True
    with pytest.raises(Exception):
        build_manual_review_handoff_record(item)


def test_deterministic_fixture_only_manual_review_handoff_output():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    assert validate_and_build_manual_review_handoff_records(items) == validate_and_build_manual_review_handoff_records(items)
