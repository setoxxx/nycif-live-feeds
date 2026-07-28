from __future__ import annotations

from dataclasses import dataclass

from scripts.nyc_location_gazetteer import NYCLocationGazetteer
from scripts.resolve_remaining_review_locations import (
    borough_for_point,
    geometry_contains,
    raw_location_candidates,
    resolve_one,
)


BOUNDARIES = [
    (
        "Brooklyn",
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [-74.10, 40.55],
                    [-73.85, 40.55],
                    [-73.85, 40.75],
                    [-74.10, 40.75],
                    [-74.10, 40.55],
                ]
            ],
        },
    ),
    (
        "Queens",
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [-73.85, 40.55],
                    [-73.65, 40.55],
                    [-73.65, 40.85],
                    [-73.85, 40.85],
                    [-73.85, 40.55],
                ]
            ],
        },
    ),
]


@dataclass
class FakeResult:
    resolved: bool
    tier: str = "tier_3_nyc_geosearch_live"
    lat: float | None = None
    lng: float | None = None
    source: str | None = "fake_geosearch"
    confidence: str | None = "high"
    confidence_reason: str | None = "Fake high-confidence result."
    label: str | None = "Fake place"


class FakeResolver:
    def __init__(self, result: FakeResult):
        self.result = result

    def resolve(self, *, display_location: str, borough: str | None = None):
        return self.result


def proposal(**overrides):
    payload = {
        "canonical_id": "review:test:1",
        "title": "Test",
        "location": "Example Center | Example Center",
        "existing_latitude": None,
        "existing_longitude": None,
        "existing_borough": None,
        "proposed_borough": None,
        "disposition": "unresolved",
        "location_classified": True,
        "pin_eligible": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "reason": "Unresolved.",
    }
    payload.update(overrides)
    return payload


def test_polygon_point_and_borough_lookup():
    assert geometry_contains(BOUNDARIES[0][1], -73.95, 40.65) is True
    assert geometry_contains(BOUNDARIES[0][1], -73.75, 40.65) is False
    assert borough_for_point(BOUNDARIES, 40.65, -73.95) == "Brooklyn"
    assert borough_for_point(BOUNDARIES, 40.65, -73.75) == "Queens"


def test_existing_coordinates_get_official_borough():
    result, changed = resolve_one(
        proposal(existing_latitude=40.65, existing_longitude=-73.95),
        boundaries=BOUNDARIES,
        gazetteer=NYCLocationGazetteer({}),
        resolver=FakeResolver(FakeResult(False)),
    )
    assert changed is True
    assert result["disposition"] == "borough_normalized_existing_coordinates"
    assert result["proposed_borough"] == "Brooklyn"
    assert result["pin_eligible"] is True


def test_live_result_must_match_existing_borough_evidence():
    result, changed = resolve_one(
        proposal(proposed_borough="Brooklyn"),
        boundaries=BOUNDARIES,
        gazetteer=NYCLocationGazetteer({}),
        resolver=FakeResolver(FakeResult(True, lat=40.65, lng=-73.75)),
    )
    assert changed is False
    assert result["disposition"] == "unresolved"


def test_live_result_maps_when_boundary_agrees():
    result, changed = resolve_one(
        proposal(proposed_borough="Brooklyn"),
        boundaries=BOUNDARIES,
        gazetteer=NYCLocationGazetteer({}),
        resolver=FakeResolver(FakeResult(True, lat=40.65, lng=-73.95)),
    )
    assert changed is True
    assert result["disposition"] == "mapped_from_live_geosearch"
    assert result["proposed_borough"] == "Brooklyn"


def test_non_geocodable_source_does_not_get_fake_pin():
    result, changed = resolve_one(
        proposal(location="Please see the Flyer | Please see the Flyer"),
        boundaries=BOUNDARIES,
        gazetteer=NYCLocationGazetteer({}),
        resolver=FakeResolver(FakeResult(True, lat=40.65, lng=-73.95)),
    )
    assert changed is False
    assert result["disposition"] == "unresolved"
    assert result["pin_eligible"] is False
    assert "no pin fabricated" in result["reason"].lower()


def test_raw_candidates_keep_specific_location_before_parent():
    candidates = raw_location_candidates("Main Pool in Crotona Park | Main Pool in Crotona Park")
    assert candidates[0] == "Main Pool in Crotona Park"
    assert "Crotona Park" in candidates
