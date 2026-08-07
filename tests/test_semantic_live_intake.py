from scripts.build_semantic_live_intake import enrich_with_location_authority, build_semantic_staged_feed
from scripts.location_evidence_contract import normalize_location_evidence


def raw_row():
    return {
        "event_id": "evt-1",
        "event_name": "Test Event",
        "event_borough": "Manhattan",
        "event_location": "1 Centre Street",
        "start_date_time": "2026-08-08T10:00:00",
        "end_date_time": "2026-08-08T12:00:00",
    }


def test_legacy_coordinate_match_never_becomes_exact_pin():
    match = {"lat": 40.7128, "lng": -74.0060}
    event = enrich_with_location_authority(raw_row(), "event_id", match)
    assert event["location_evidence"]["validation_state"] == "unvalidated"
    assert event["location_evidence"]["exact_pin_eligible"] is False
    assert event["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert event["certified_pin"] is False
    assert event["needs_review"] is True


def test_validated_resolver_evidence_becomes_map_ready():
    match = {
        "lat": 40.7128,
        "lng": -74.0060,
        "resolver_tier": "exact_address",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "geocoder_source": "nyc_geosearch",
        "reason_code": "address_and_borough_validated",
    }
    event = enrich_with_location_authority(raw_row(), "exact_address", match)
    assert event["map_eligibility_state"] == "MAP_READY"
    assert event["certified_pin"] is True
    assert event["needs_review"] is False


def test_unresolved_match_is_list_only():
    evidence = normalize_location_evidence("none", None)
    assert evidence["tier"] == "unresolved"
    assert evidence["exact_pin_eligible"] is False


def test_staging_accepts_only_certified_map_ready_rows():
    certified = enrich_with_location_authority(
        raw_row(),
        "exact_address",
        {
            "lat": 40.7128,
            "lng": -74.0060,
            "resolver_tier": "exact_address",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "geocoder_source": "nyc_geosearch",
        },
    )
    legacy = enrich_with_location_authority(raw_row(), "event_id", {"lat": 40.7130, "lng": -74.0062})
    feed = {"events": [certified, legacy]}
    staged, manifest = build_semantic_staged_feed(feed)
    assert len(staged["events"]) == 1
    assert staged["events"][0]["certified_pin"] is True
    assert staged["events"][0]["location_evidence"]["exact_pin_eligible"] is True
    assert manifest["coordinates_without_exact_evidence_promoted"] == 0
    assert manifest["all_staged_rows_certified"] is True
