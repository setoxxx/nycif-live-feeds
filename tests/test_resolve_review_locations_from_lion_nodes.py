from __future__ import annotations

from scripts import resolve_review_locations_from_lion_nodes as lion


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


def proposal():
    return {
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


def report():
    return {
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


def test_distinctive_query_token_avoids_generic_street_words():
    assert lion.distinctive_query_token("WEST 48 STREET") == "48"
    assert lion.distinctive_query_token("BRUCKNER BOULEVARD") == "BRUCKNER"
    assert lion.distinctive_query_token("AVENUE OF THE AMERICAS") == "AMERICAS"


def test_intersection_label_must_contain_both_streets():
    assert lion.label_matches_intersection("W 48 ST / AVENUE OF THE AMERICAS", "WEST 48 STREET", "6 AVENUE")
    assert not lion.label_matches_intersection("W 48 ST / 7 AVE", "WEST 48 STREET", "6 AVENUE")
    assert not lion.label_matches_intersection("W 48 ST / 6 AVE", "WEST 49 STREET", "6 AVENUE")


def test_fetch_intersection_nodes_records_service_error(monkeypatch):
    def fail(_url, _params):
        raise RuntimeError("temporary node service failure")

    monkeypatch.setattr(lion, "arcgis_get", fail)
    nodes, diagnostic = lion.fetch_intersection_nodes(
        "WEST 48 STREET",
        "6 AVENUE",
        request_cache={},
    )
    assert nodes == []
    assert "temporary node service failure" in diagnostic["service_error"]


def test_resolve_payload_uses_current_lion_intersection_nodes(monkeypatch):
    first = [
        {
            "node_id": "100",
            "latitude": 40.7585,
            "longitude": -73.9810,
            "v_intersect": "W 48 ST / AVENUE OF THE AMERICAS",
        }
    ]
    second = [
        {
            "node_id": "101",
            "latitude": 40.7602,
            "longitude": -73.9838,
            "v_intersect": "W 48 ST / 7 AVE",
        }
    ]

    def fake_fetch(street1, street2, *, request_cache):
        del request_cache
        nodes = first if "6" in street2 else second
        return nodes, {"street_1": street1, "street_2": street2, "verified_node_count": 1}

    monkeypatch.setattr(lion, "fetch_intersection_nodes", fake_fetch)
    boundaries = [("Manhattan", square(-74.02, 40.70, -73.90, 40.88))]
    final_report, final_payload = lion.resolve_payload(
        report(),
        {"target_count": 1, "proposals": [proposal()]},
        boundaries=boundaries,
    )
    result = final_payload["proposals"][0]
    assert result["disposition"] == "mapped_from_nyc_lion_intersection_nodes"
    assert result["lion_endpoint_node_ids"] == ["100", "101"]
    assert result["proposed_borough"] == "Manhattan"
    assert final_report["unresolved_count"] == 0
    assert final_report["lion_resolution"]["newly_resolved_count"] == 1


def test_cross_borough_endpoint_is_rejected(monkeypatch):
    first = [
        {
            "node_id": "100",
            "latitude": 40.7585,
            "longitude": -73.9810,
            "v_intersect": "W 48 ST / AVENUE OF THE AMERICAS",
        }
    ]
    second = [
        {
            "node_id": "200",
            "latitude": 40.70,
            "longitude": -73.80,
            "v_intersect": "W 48 ST / 7 AVE",
        }
    ]

    def fake_fetch(_street1, street2, *, request_cache):
        del request_cache
        return (first if "6" in street2 else second), {"verified_node_count": 1}

    monkeypatch.setattr(lion, "fetch_intersection_nodes", fake_fetch)
    boundaries = [
        ("Manhattan", square(-74.02, 40.70, -73.90, 40.88)),
        ("Queens", square(-73.90, 40.60, -73.70, 40.90)),
    ]
    final_report, final_payload = lion.resolve_payload(
        report(),
        {"target_count": 1, "proposals": [proposal()]},
        boundaries=boundaries,
    )
    assert final_payload["proposals"][0]["disposition"] == "unresolved"
    assert final_report["unresolved_count"] == 1
