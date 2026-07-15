"""Pin integrity — ocean / Null Island / swap / OOB cannot remain map_ready."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pin_integrity import (  # noqa: E402
    REASON_NULL_ISLAND,
    REASON_OK,
    REASON_OK_SWAP,
    REASON_OOB,
    REASON_SWAP_SUSPECTED,
    certify_event_pin,
    certify_nyc_pin,
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
    # Mid-Atlantic roughly east of NYC
    lat, _lng, ok, reason = certify_nyc_pin(40.5, -70.0)
    assert not ok
    assert reason == REASON_OOB
    assert lat is None


def test_mainland_us_false_pin_rejected():
    # Chicago
    _lat, _lng, ok, reason = certify_nyc_pin(41.88, -87.63)
    assert not ok
    assert reason == REASON_OOB


def test_unambiguous_swap_auto_correct():
    # Stored as lng,lat flipped — as-is OOB, swapped in NYC box.
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


def test_green_path_keeps_certified_map_ready():
    event = {
        "coordinate_status": "map_ready",
        "latitude": 40.7128,
        "longitude": -74.0060,
    }
    result = certify_event_pin(event)
    assert not result.get("demoted")
    assert event["coordinate_status"] == "map_ready"
    assert event["certified_pin"] is True
    assert abs(float(event["latitude"]) - 40.7128) < 1e-9


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
