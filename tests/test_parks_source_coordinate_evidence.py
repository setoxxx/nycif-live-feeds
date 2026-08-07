from scripts.sync_nyc_parks_bigapps_events import normalize_event_item
from scripts.pin_integrity import evaluate_map_eligibility


def test_parks_official_coordinate_is_explicit_exact_evidence():
    row = normalize_event_item(
        {
            "guid": "parks-1",
            "title": "Test Parks Event",
            "startdate": "2026-08-08",
            "starttime": "10:00:00",
            "coordinates": "40.7829,-73.9654",
            "location": "Central Park",
        }
    )
    evidence = row["location_evidence"]
    assert evidence["tier"] == "exact_source_coordinate"
    assert evidence["validation_state"] == "validated"
    assert evidence["exact_pin_eligible"] is True
    assert evidence["source_provenance"]

    decision = evaluate_map_eligibility(row)
    assert decision["map_eligibility"] == "MAP_READY"
    assert decision["exact_pin_eligible"] is True


def test_parks_missing_or_bad_coordinate_never_invents_exact_evidence():
    for coordinate in (None, "", "not-a-coordinate", "0,0", "91,181"):
        row = normalize_event_item(
            {
                "guid": "parks-2",
                "title": "Unlocated Parks Event",
                "startdate": "2026-08-08",
                "coordinates": coordinate,
                "location": "A park",
            }
        )
        assert row["lat"] is None
        assert row["lng"] is None
        assert row["location_evidence"] is None
        decision = evaluate_map_eligibility(row)
        assert decision["map_eligibility"] == "LIST_ONLY"
        assert decision["exact_pin_eligible"] is False
