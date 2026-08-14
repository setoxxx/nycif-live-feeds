from scripts.sync_nyc_parks_bigapps_events import normalize_event_item
from scripts.pin_integrity import evaluate_map_eligibility
from scripts.projector_v2_authority import semantic_map_decision


def test_parks_official_coordinate_is_preserved_but_site_validation_is_pending():
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
    assert row["lat"] == 40.7829
    assert row["lng"] == -73.9654
    assert evidence["tier"] == "exact_source_coordinate"
    assert evidence["validation_state"] == "unvalidated"
    assert evidence["site_validation_state"] == "pending"
    assert evidence["exact_pin_eligible"] is False
    assert evidence["source_provenance"]
    assert evidence["source_event_id"] == "parks-1"

    decision = evaluate_map_eligibility(row)
    assert decision["map_eligibility"] == "REVIEW_REQUIRED"
    assert decision["exact_pin_eligible"] is False

    public_decision = semantic_map_decision(row)
    assert public_decision["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert public_decision["certified_pin"] is False
    assert public_decision["latitude"] is None
    assert public_decision["longitude"] is None


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
