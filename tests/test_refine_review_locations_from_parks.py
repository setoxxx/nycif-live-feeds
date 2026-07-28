from __future__ import annotations

from scripts import refine_review_locations_from_parks as parks


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


def proposal(**overrides):
    row = {
        "canonical_id": "review:little-bay",
        "title": "Silent Disco On The Bay",
        "date": "2026-07-24",
        "location": "Little Bay Park - Parking lot, lot under the bridge.",
        "disposition": "unresolved",
        "location_classified": True,
        "pin_eligible": False,
        "promotion_allowed": False,
        "public_map_modified": False,
    }
    row.update(overrides)
    return row


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


def parks_event(**overrides):
    row = {
        "title": "Silent Disco On The Bay",
        "start_date": "2026-07-24",
        "display_location": "Little Bay Park",
        "location": "Little Bay Park",
        "description": "Little Bay Park Parking Lot Under Bridge",
        "lat": 40.78960037231445,
        "lng": -73.78700256347656,
        "source_event_id": "2209999",
        "link": "https://www.nycgovparks.org/events/2026/07/24/silent-disco-on-the-bay",
        "park_ids": "Q010A",
        "park_names": ["Little Bay Park"],
    }
    row.update(overrides)
    return row


def test_exact_title_date_and_location_resolves_little_bay():
    boundaries = [("Queens", square(-73.90, 40.70, -73.70, 40.90))]
    final_report, final_payload = parks.refine_payload(
        report(),
        {"target_count": 1, "proposals": [proposal()]},
        [parks_event()],
        boundaries=boundaries,
    )
    result = final_payload["proposals"][0]
    assert result["disposition"] == "mapped_from_nyc_parks_counterpart"
    assert result["proposed_borough"] == "Queens"
    assert result["proposed_latitude"] == 40.78960037231445
    assert result["proposed_longitude"] == -73.78700256347656
    assert result["parks_counterpart_source_event_ids"] == ["2209999"]
    assert final_report["unresolved_count"] == 0
    assert final_report["parks_counterpart_refinement"]["newly_resolved_count"] == 1


def test_wrong_date_does_not_resolve():
    boundaries = [("Queens", square(-73.90, 40.70, -73.70, 40.90))]
    final_report, final_payload = parks.refine_payload(
        report(),
        {"target_count": 1, "proposals": [proposal()]},
        [parks_event(start_date="2026-07-17")],
        boundaries=boundaries,
    )
    assert final_payload["proposals"][0]["disposition"] == "unresolved"
    assert final_report["unresolved_count"] == 1


def test_generic_location_without_distinctive_tokens_does_not_resolve():
    boundaries = [("Queens", square(-73.90, 40.70, -73.70, 40.90))]
    final_report, final_payload = parks.refine_payload(
        report(),
        {"target_count": 1, "proposals": [proposal(location="Parking lot under bridge")]},
        [parks_event(display_location="Parking lot", location="Parking lot", description="Parking lot under bridge")],
        boundaries=boundaries,
    )
    assert final_payload["proposals"][0]["disposition"] == "unresolved"
    assert final_report["unresolved_count"] == 1


def test_cross_borough_counterparts_are_rejected_as_ambiguous():
    boundaries = [
        ("Queens", square(-73.90, 40.70, -73.70, 40.90)),
        ("Staten Island", square(-74.30, 40.45, -74.05, 40.70)),
    ]
    evidence = [
        parks_event(),
        parks_event(
            source_event_id="other",
            lat=40.60,
            lng=-74.15,
        ),
    ]
    final_report, final_payload = parks.refine_payload(
        report(),
        {"target_count": 1, "proposals": [proposal()]},
        evidence,
        boundaries=boundaries,
    )
    assert final_payload["proposals"][0]["disposition"] == "unresolved"
    assert final_report["unresolved_count"] == 1
