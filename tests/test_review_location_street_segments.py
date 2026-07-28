from __future__ import annotations

from dataclasses import dataclass

from scripts.run_review_location_resolution_audit import (
    parse_street_segment,
    resolve_street_segment_proposal,
)


@dataclass
class Result:
    resolved: bool
    lat: float | None
    lng: float | None
    label: str | None


class FakeResolver:
    def __init__(self, results):
        self.results = results

    def resolve(self, *, display_location, borough=None, cache_keys=None):
        return self.results.get(
            display_location,
            Result(False, None, None, None),
        )


def square(lng1, lat1, lng2, lat2):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lng1, lat1],
                [lng2, lat1],
                [lng2, lat2],
                [lng1, lat2],
                [lng1, lat1],
            ]
        ],
    }


def test_parse_between_location_and_borough_suffix():
    parsed = parse_street_segment(
        "WEST 48 STREET between 6 AVENUE and 7 AVENUE Manhattan | duplicate"
    )
    assert parsed == ("WEST 48 STREET", "6 AVENUE", "7 AVENUE", "Manhattan")


def test_two_valid_endpoints_produce_midpoint_pin():
    proposal = {
        "canonical_id": "calendar:soldier-ride",
        "title": "2026 Soldier Ride New York",
        "location": "WEST 48 STREET between 6 AVENUE and 7 AVENUE Manhattan",
        "proposed_borough": "Manhattan",
        "disposition": "unresolved",
        "existing_latitude": None,
        "existing_longitude": None,
    }
    resolver = FakeResolver(
        {
            "WEST 48 STREET and 6 AVENUE": Result(True, 40.7585, -73.9810, "W 48 St & 6 Ave"),
            "WEST 48 STREET and 7 AVENUE": Result(True, 40.7602, -73.9838, "W 48 St & 7 Ave"),
        }
    )
    boundaries = [("Manhattan", square(-74.02, 40.70, -73.90, 40.88))]
    result = resolve_street_segment_proposal(
        proposal,
        boundaries=boundaries,
        resolver=resolver,
    )
    assert result is not None
    assert result["disposition"] == "mapped_from_street_segment_endpoints"
    assert result["proposed_borough"] == "Manhattan"
    assert result["proposed_latitude"] == 40.75935
    assert result["proposed_longitude"] == -73.9824
    assert result["street_segment_length_m"] > 10


def test_cross_borough_endpoint_rejects_segment():
    proposal = {
        "canonical_id": "calendar:test",
        "title": "Test",
        "location": "MAIN STREET between FIRST STREET and SECOND STREET Manhattan",
        "proposed_borough": "Manhattan",
        "disposition": "unresolved",
        "existing_latitude": None,
        "existing_longitude": None,
    }
    resolver = FakeResolver(
        {
            "MAIN STREET and FIRST STREET": Result(True, 40.75, -73.98, "First"),
            "MAIN STREET and SECOND STREET": Result(True, 40.75, -73.80, "Second"),
        }
    )
    boundaries = [
        ("Manhattan", square(-74.02, 40.70, -73.90, 40.88)),
        ("Queens", square(-73.89, 40.70, -73.70, 40.88)),
    ]
    assert (
        resolve_street_segment_proposal(
            proposal,
            boundaries=boundaries,
            resolver=resolver,
        )
        is None
    )
