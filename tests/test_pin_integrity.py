"""Pin integrity — geometry validity is not semantic location certification."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pin_integrity import (  # noqa: E402
    REASON_EXACT_ELIGIBLE,
    REASON_LEGACY_EVIDENCE,
    REASON_NULL_ISLAND,
    REASON_OK,
    REASON_OK_SWAP,
    REASON_OOB,
    REASON_SWAP_SUSPECTED,
    certify_event_pin,
    certify_nyc_pin,
    evaluate_map_eligibility,
)


def test_valid_nyc_pin_green_path():
    lat, lng, ok, reason = certify_nyc_pin(40.758, -73.985)
    assert ok
    assert reason == REASON_OK
    assert abs(lat - 40.758) < 1e-9
    assert abs(lng - (-73.985)) < 1e-9


def test_null_island_rejected():
    lat, lng, ok, reason = certify_nyc_pin(0, 0)
    assert not ok
    assert reason == REASON_NULL_ISLAND
    assert lat is None and lng is None


def test_ocean_oob_rejected():
    lat, _lng, ok, reason = certify_nyc_pin(40.5, -70.0)
    assert not ok
    assert reason == REASON_OOB
    assert lat is None


def test_mainland_us_false_pin_rejected():
    _lat, _lng, ok, reason = certify_nyc_pin(41.88, -87.63)
    assert not ok
    assert reason == REASON_OOB


def test_unambiguous_swap_auto_correct():
    lat, lng, ok, reason = certify_nyc_pin(-73.985, 40.758)
    assert ok
    assert reason == REASON_OK_SWAP
    assert abs(lat - 40.758) < 1e-9
    assert abs(lng - (-73.985)) < 1e-9


def test_swap_suspected_without_correct_when_disabled():
    lat, _lng, ok, reason = certify_nyc_pin(-73.985, 40.758, allow_swap_correct=False)
    assert not ok
    assert reason in {REASON_SWAP_SUSPECTED, REASON_OOB}
    assert lat is None


def test_demote_bad_map_ready_clears_coords():
    event = {
        "id": "ocean-1",
        "title": "Ocean pin",
        "coordinate_status": "map_ready",
        "latitude": 40.5,
        "longitude": -70.0,
    }
    result = certify_event_pin(event)
    assert result.get("demoted")
    assert event["coordinate_status"] == "list_only"
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event.get("certified_pin") is False
    assert event.get("map_link") is None


def test_null_island_map_ready_demoted():
    event = {
        "coordinate_status": "map_ready",
        "latitude": 0.0,
        "longitude": 0.0,
        "lat": 0.0,
        "lng": 0.0,
    }
    certify_event_pin(event)
    assert event["coordinate_status"] == "list_only"
    assert event["lat"] is None and event["lng"] is None


def test_bounding_box_only_coordinate_cannot_create_certified_pin():
    event = {
        "coordinate_status": "map_ready",
        "latitude": 40.7128,
        "longitude": -74.0060,
    }
    eligibility = evaluate_map_eligibility(event)
    assert eligibility["geometry_valid"] is True
    assert eligibility["map_eligibility"] == "REVIEW_REQUIRED"
    assert eligibility["reason_code"] == REASON_LEGACY_EVIDENCE
    assert eligibility["exact_pin_eligible"] is False

    result = certify_event_pin(event)
    assert result["status"] == "legacy_evidence_pending_migration"
    assert event["coordinate_status"] == "map_ready"
    assert event["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert event["certified_pin"] is False


def test_validated_source_coordinate_can_certify_exact_pin():
    event = {
        "coordinate_status": "map_ready",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "location_evidence": {
            "tier": "exact_source_coordinate",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "source_provenance": "source_provided",
        },
    }
    eligibility = evaluate_map_eligibility(event)
    assert eligibility["map_eligibility"] == "MAP_READY"
    assert eligibility["reason_code"] == REASON_EXACT_ELIGIBLE
    assert eligibility["exact_pin_eligible"] is True

    result = certify_event_pin(event)
    assert result["status"] == "map_ready"
    assert event["map_eligibility_state"] == "MAP_READY"
    assert event["certified_pin"] is True


def test_unvalidated_geocoder_candidate_cannot_certify_exact_pin():
    event = {
        "coordinate_status": "map_ready",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "location_evidence": {
            "tier": "exact_address",
            "validation_state": "unvalidated",
            "exact_pin_eligible": False,
            "geocoder_provenance": "nyc_geosearch_planninglabs",
        },
    }
    eligibility = evaluate_map_eligibility(event)
    assert eligibility["map_eligibility"] == "REVIEW_REQUIRED"
    assert eligibility["exact_pin_eligible"] is False


def test_shoot_day_magnet_rank_prefers_parade_over_greenmarket():
    from build_photographer_shoot_day_certified import magnet_rank

    parade = {
        "title": "Puerto Rican Day Parade",
        "recurrence_label": "returning_likely",
        "assignment_score": 200,
    }
    market = {
        "title": "Union Square Greenmarket",
        "recurrence_label": "returning_likely",
        "assignment_score": 400,
    }
    assert magnet_rank(parade) < magnet_rank(market)
