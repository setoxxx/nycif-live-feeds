from __future__ import annotations

from scripts import resolve_review_locations_from_lion as lion


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


def test_street_normalization_and_aliases():
    assert lion.street_key("WEST 48 STREET") == "W 48 ST"
    assert lion.street_key("Third Avenue") == "3 AVE"
    assert "AVENUE OF THE AMERICAS" in lion.street_variants("6 Avenue")
    assert lion.street_key("East Fordham Road") == "E FORDHAM RD"


def test_parse_segment_location():
    assert lion.parse_segment_location(
        "WEST 48 STREET between 6 AVENUE and 7 AVENUE Manhattan | duplicate"
    ) == ("WEST 48 STREET", "6 AVENUE", "7 AVENUE", "Manhattan")


def test_node_street_index_finds_shared_intersections():
    rows = [
        {
            "Street": "W 48 ST",
            "SAFStreetName": None,
            "NodeIDFrom": "100",
            "NodeIDTo": "101",
        },
        {
            "Street": "AVENUE OF THE AMERICAS",
            "SAFStreetName": "6 AVE",
            "NodeIDFrom": "100",
            "NodeIDTo": "110",
        },
        {
            "Street": "7 AVE",
            "SAFStreetName": None,
            "NodeIDFrom": "101",
            "NodeIDTo": "111",
        },
    ]
    index = lion.node_street_index(rows)
    assert lion.matching_nodes(index, "WEST 48 STREET", "6 AVENUE") == {"100"}
    assert lion.matching_nodes(index, "WEST 48 STREET", "7 AVENUE") == {"101"}


def test_choose_shortest_valid_endpoint_pair():
    boundaries = [("Manhattan", square(-74.02, 40.70, -73.90, 40.88))]
    points = {
        "100": {"node_id": "100", "latitude": 40.7585, "longitude": -73.9810, "v_intersect": "6 AVE"},
        "101": {"node_id": "101", "latitude": 40.7602, "longitude": -73.9838, "v_intersect": "7 AVE"},
        "102": {"node_id": "102", "latitude": 40.8100, "longitude": -73.9500, "v_intersect": "far"},
    }
    pair = lion.choose_endpoint_pair(
        {"100", "102"},
        {"101"},
        points,
        borough="Manhattan",
        boundaries=boundaries,
    )
    assert pair is not None
    assert pair["first"]["node_id"] == "100"
    assert pair["second"]["node_id"] == "101"
    assert pair["midpoint_latitude"] == 40.75935


def test_resolve_payload_uses_lion_nodes(monkeypatch):
    proposal = {
        "canonical_id": "calendar:soldier-ride",
        "title": "2026 Soldier Ride New York",
        "location": "WEST 48 STREET between 6 AVENUE and 7 AVENUE Manhattan",
        "proposed_borough": "Manhattan",
        "disposition": "unresolved",
        "location_classified": True,
        "pin_eligible": False,
        "promotion_allowed": False,
        "public_map_modified": False,
    }
    rows = [
        {"OBJECTID": 1, "Street": "W 48 ST", "SAFStreetName": None, "NodeIDFrom": "100", "NodeIDTo": "101"},
        {"OBJECTID": 2, "Street": "AVENUE OF THE AMERICAS", "SAFStreetName": "6 AVE", "NodeIDFrom": "100", "NodeIDTo": "110"},
        {"OBJECTID": 3, "Street": "7 AVE", "SAFStreetName": None, "NodeIDFrom": "101", "NodeIDTo": "111"},
    ]
    points = {
        "100": {"node_id": "100", "latitude": 40.7585, "longitude": -73.9810, "v_intersect": "W 48 ST / 6 AVE"},
        "101": {"node_id": "101", "latitude": 40.7602, "longitude": -73.9838, "v_intersect": "W 48 ST / 7 AVE"},
    }
    monkeypatch.setattr(lion, "fetch_lion_lines", lambda borough, requested: rows)
    monkeypatch.setattr(lion, "fetch_node_points", lambda node_ids: points)

    report = {
        "target_null_borough_count": 1,
        "source_generated_at_utc": "2026-07-28T12:25:24Z",
        "safety": {
            "public_map_modified": False,
            "production_feed_modified": False,
            "location_cache_modified": False,
            "wordpress_modified": False,
            "promotion_allowed": False,
            "proposal_only": True,
        },
    }
    payload = {"target_count": 1, "proposals": [proposal]}
    boundaries = [("Manhattan", square(-74.02, 40.70, -73.90, 40.88))]
    final_report, final_payload = lion.resolve_payload(report, payload, boundaries=boundaries)
    result = final_payload["proposals"][0]
    assert result["disposition"] == "mapped_from_nyc_lion_nodes"
    assert result["lion_endpoint_node_ids"] == ["100", "101"]
    assert final_report["unresolved_count"] == 0
    assert final_report["lion_resolution"]["newly_resolved_count"] == 1
