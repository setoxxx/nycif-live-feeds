import pytest

from tools.registry.xri_g40_fixture_only_source_ingestion_scaffold import (
    FixtureOnlyScaffoldError,
    normalize_fixture_record,
    normalize_fixture_records,
)


def payload():
    return {
        "group_key": "fixture-group",
        "display_location": "Fixture Location",
        "candidate_identity": "fixture-001",
        "review_rank": 1,
    }


def test_fixture_only_normalization_pass():
    result = normalize_fixture_record(payload())
    assert result.group_key == "fixture-group"
    assert result.display_location == "Fixture Location"
    assert result.candidate_identity == "fixture-001"


def test_stable_identity_required():
    item = payload()
    item.pop("candidate_identity")
    with pytest.raises(FixtureOnlyScaffoldError):
        normalize_fixture_record(item)


def test_review_rank_is_display_only_not_identity():
    item = payload()
    item["review_rank"] = 99
    result = normalize_fixture_record(item)
    assert result.candidate_identity == "fixture-001"
    assert result.display["review_rank_identity_use"] == "forbidden_display_only"


@pytest.mark.parametrize("field", ["live_url", "api_url", "soda_endpoint", "nyc_open_data_endpoint"])
def test_live_fetch_targets_rejected(field):
    item = payload()
    item[field] = "blocked-target"
    with pytest.raises(FixtureOnlyScaffoldError):
        normalize_fixture_record(item)


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
        "location_cache_access",
    ],
)
def test_forbidden_actions_rejected(field):
    item = payload()
    item[field] = True
    with pytest.raises(FixtureOnlyScaffoldError):
        normalize_fixture_record(item)


def test_deterministic_fixture_only_output():
    items = [payload(), {**payload(), "candidate_identity": "fixture-002"}]
    assert normalize_fixture_records(items) == normalize_fixture_records(items)
