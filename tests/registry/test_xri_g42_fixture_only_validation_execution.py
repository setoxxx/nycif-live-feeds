import pytest

from tools.registry.xri_g41_fixture_only_parser_normalizer import FixtureOnlyParserNormalizerError
from tools.registry.xri_g42_fixture_only_validation_execution import (
    parse_and_validate_fixture_records,
    validate_fixture_record,
    validate_fixture_records,
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


def test_fixture_only_validation_execution_pass():
    result = validate_fixture_record(payload())
    assert result.valid is True
    assert result.group_key == "fixture-group"
    assert result.display_location == "Fixture Location"


def test_accepts_list_and_single_fixture_input():
    assert len(validate_fixture_records(payload())) == 1
    assert len(validate_fixture_records([payload(), {**payload(), "candidate_identity": "fixture-002"}])) == 2


def test_stable_identity_required():
    item = payload()
    item.pop("candidate_identity")
    with pytest.raises(FixtureOnlyParserNormalizerError):
        validate_fixture_record(item)


def test_review_rank_is_not_identity():
    result = validate_fixture_record({**payload(), "review_rank": 99})
    assert result.candidate_identity == "fixture-001"
    assert result.normalized["display"]["review_rank_identity_use"] == "forbidden_display_only"


def test_normalized_fields_are_deterministic():
    result = validate_fixture_record(payload())
    assert result.normalized["start"] == "2026-07-06T10:00:00"
    assert result.normalized["end"] == "2026-07-06T11:00:00"
    assert result.normalized["source_name"] == "Test Source"
    assert result.normalized["event_name"] == "Fixture Event"
    assert result.normalized["display_location"] == "Fixture Location"


def test_flagged_fixture_rejected():
    item = payload()
    item["production_target"] = True
    with pytest.raises(FixtureOnlyParserNormalizerError):
        validate_fixture_record(item)


def test_deterministic_fixture_only_validation_output():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    assert parse_and_validate_fixture_records(items) == parse_and_validate_fixture_records(items)
