from scripts.sync_nyc_parks_bigapps_events import normalize_event_item
from scripts.pin_integrity import evaluate_map_eligibility


def test_parks_official_coordinate_is_explicit_exact_evidence():
    row = normalize_event_item(
        {
            "event_id": "parks-1",
            "title": "Test Parks Event",
            "date": "2026-08-10",
            "start_time": "10:00 AM",
        },
        [
            {
                "event_id": "parks-1",
                "name": "Central Park",
                "lat": "40.7829",
                "long": "-73.9654",
                "borough": "Manhattan",
            }
        ],
        [],
    )
    evidence = row["location_evidence"]
    assert evidence["tier"] == "exact_source_coordinate"
    assert evidence["validation_state"] == "validated"
    assert evidence["exact_pin_eligible"] is True
    assert evidence["source_provenance"]
    assert evidence["join_key"] == "event_id"

    decision = evaluate_map_eligibility(row)
    assert decision["map_eligibility"] == "MAP_READY"
    assert decision["exact_pin_eligible"] is True


def test_parks_multiple_official_points_abstain_from_exact_evidence():
    row = normalize_event_item(
        {"event_id": "parks-2", "title": "Multi-location Parks Event", "date": "2026-08-10"},
        [
            {"event_id": "parks-2", "name": "A", "lat": "40.7001", "long": "-73.9001"},
            {"event_id": "parks-2", "name": "B", "lat": "40.7101", "long": "-73.9101"},
        ],
        [],
    )
    assert row["lat"] is None
    assert row["lng"] is None
    assert row["location_evidence"] is None
    assert row["source_coordinate_state"] == "multiple_source_location_points"
    decision = evaluate_map_eligibility(row)
    assert decision["map_eligibility"] == "LIST_ONLY"
    assert decision["exact_pin_eligible"] is False


def test_parks_missing_or_bad_coordinate_never_invents_exact_evidence():
    for location in (
        {"event_id": "parks-3"},
        {"event_id": "parks-3", "lat": "0", "long": "0"},
        {"event_id": "parks-3", "lat": "not-a-coordinate", "long": "-73.9"},
    ):
        row = normalize_event_item(
            {"event_id": "parks-3", "title": "Unlocated Parks Event", "date": "2026-08-10"},
            [location],
            [],
        )
        assert row["lat"] is None
        assert row["lng"] is None
        assert row["location_evidence"] is None
        decision = evaluate_map_eligibility(row)
        assert decision["map_eligibility"] == "LIST_ONLY"
        assert decision["exact_pin_eligible"] is False
