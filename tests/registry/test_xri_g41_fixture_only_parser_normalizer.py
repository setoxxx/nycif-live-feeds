import pytest

from tools.registry.xri_g41_fixture_only_parser_normalizer import (
    FixtureOnlyParserNormalizerError,
    parse_normalize_fixture_record,
    parse_normalize_fixture_records,
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


def test_fixture_only_parser_normalizer_pass():
    result = parse_normalize_fixture_record(payload())
    assert result.group_key == "fixture-group"
    assert result.display_location == "Fixture Location"
    assert result.candidate_identity == "fixture-001"


def test_accepts_list_and_single_fixture_input():
    single = parse_normalize_fixture_records(payload())
    many = parse_normalize_fixture_records([payload(), {**payload(), "candidate_identity": "fixture-002"}])
    assert len(single) == 1
    assert len(many) == 2


def test_stable_identity_required():
    item = payload()
    item.pop("candidate_identity")
    with pytest.raises(FixtureOnlyParserNormalizerError):
        parse_normalize_fixture_record(item)


def test_review_rank_is_not_identity():
    item = payload()
    item["review_rank"] = 99
    result = parse_normalize_fixture_record(item)
    assert result.candidate_identity == "fixture-001"
    assert result.normalized["display"]["review_rank_identity_use"] == "forbidden_display_only"


def test_date_time_fixture_fields_normalized_deterministically():
    result = parse_normalize_fixture_record(payload())
    assert result.normalized["start"] == "2026-07-06T10:00:00"
    assert result.normalized["end"] == "2026-07-06T11:00:00"


def test_source_title_location_fields_normalized_deterministically():
    result = parse_normalize_fixture_record(payload())
    assert result.normalized["source_name"] == "Test Source"
    assert result.normalized["event_name"] == "Fixture Event"
    assert result.normalized["display_location"] == "Fixture Location"


@pytest.mark.parametrize("field", ["live_url", "api_url", "soda_endpoint", "nyc_open_data_endpoint"])
def test_external_source_targets_rejected(field):
    item = payload()
    item[field] = "blocked-target"
    with pytest.raises(FixtureOnlyParserNormalizerError):
        parse_normalize_fixture_record(item)


@pytest.mark.parametrize(
    "field",
    [
        "requires_geocoding",
        "registry_write",
        "registry_import",
        "approval",
        "promotion",
        "publishing",
        "public_map_runtime",
        "public_map_output",
        "scheduled_workflow",
        "location_cache_access",
    ],
)
def test_blocked_actions_rejected(field):
    item = payload()
    item[field] = True
    with pytest.raises(FixtureOnlyParserNormalizerError):
        parse_normalize_fixture_record(item)


def test_deterministic_fixture_only_output():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    assert parse_normalize_fixture_records(items) == parse_normalize_fixture_records(items)
