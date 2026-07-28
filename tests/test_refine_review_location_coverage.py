from __future__ import annotations

from scripts.refine_review_location_coverage import (
    build_evidence_index,
    location_candidates,
    refine_one,
)


def proposal(**overrides):
    payload = {
        "canonical_id": "review:test:1",
        "title": "Test",
        "location": "Main Pool in Example Park | Main Pool in Example Park",
        "existing_latitude": None,
        "existing_longitude": None,
        "existing_borough": None,
        "disposition": "unresolved",
        "location_classified": True,
        "pin_eligible": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "reason": "No reliable evidence.",
    }
    payload.update(overrides)
    return payload


def test_location_candidates_split_duplicate_joined_fields():
    keys = location_candidates("Astoria Pool in Astoria Park | Astoria Pool in Astoria Park")
    assert "astoria pool in astoria park" in keys
    assert "astoria park" in keys
    assert len(keys) == len(set(keys))


def test_refines_exact_location_with_unique_tight_cluster():
    unresolved = proposal(location="Kosciuszko Pool | Kosciuszko Pool")
    evidence = {
        "kosciuszko pool": [
            {"borough": "Brooklyn", "lat": 40.6911, "lng": -73.9497, "source": "a"},
            {"borough": "Brooklyn", "lat": 40.69111, "lng": -73.94969, "source": "b"},
        ]
    }
    result, changed = refine_one(unresolved, evidence)
    assert changed is True
    assert result["disposition"] == "mapped_from_internal_location_evidence"
    assert result["proposed_borough"] == "Brooklyn"
    assert result["pin_eligible"] is True


def test_does_not_map_cross_borough_location_evidence():
    unresolved = proposal(location="Shared Name")
    evidence = {
        "shared name": [
            {"borough": "Brooklyn", "lat": 40.68, "lng": -73.96, "source": "a"},
            {"borough": "Queens", "lat": 40.75, "lng": -73.84, "source": "b"},
        ]
    }
    result, changed = refine_one(unresolved, evidence)
    assert changed is False
    assert result["disposition"] == "unresolved"


def test_does_not_map_dispersed_coordinates():
    unresolved = proposal(location="Large Park")
    evidence = {
        "large park": [
            {"borough": "Brooklyn", "lat": 40.65, "lng": -73.98, "source": "a"},
            {"borough": "Brooklyn", "lat": 40.67, "lng": -73.96, "source": "b"},
        ]
    }
    result, changed = refine_one(unresolved, evidence)
    assert changed is False
    assert result["disposition"] == "unresolved"
    assert result["proposed_borough"] == "Brooklyn"
    assert "too dispersed" in result["reason"]


def test_existing_coordinates_keep_original_pin_when_same_location_agrees():
    unresolved = proposal(
        location="Herald Square | Herald Square",
        existing_latitude=40.7505,
        existing_longitude=-73.9878,
    )
    evidence = {
        "herald square": [
            {"borough": "Manhattan", "lat": 40.7506, "lng": -73.9879, "source": "a"},
        ]
    }
    result, changed = refine_one(unresolved, evidence)
    assert changed is True
    assert result["disposition"] == "borough_normalized_existing_coordinates"
    assert result["proposed_borough"] == "Manhattan"
    assert result["proposed_latitude"] == 40.7505


def test_build_evidence_uses_known_review_and_resolved_proposals():
    review = [
        {
            "borough": "Queens",
            "location": "Astoria Pool in Astoria Park",
            "latitude": 40.7798,
            "longitude": -73.9230,
        }
    ]
    resolved = [
        proposal(
            location="Kosciuszko Pool",
            disposition="borough_normalized_existing_coordinates",
            proposed_borough="Brooklyn",
            proposed_latitude=40.6911,
            proposed_longitude=-73.9497,
        )
    ]
    index = build_evidence_index(review, resolved)
    assert {row["borough"] for row in index["astoria pool in astoria park"]} == {"Queens"}
    assert {row["borough"] for row in index["kosciuszko pool"]} == {"Brooklyn"}
