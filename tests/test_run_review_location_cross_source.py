from __future__ import annotations

from scripts.run_review_location_cross_source import evidence_from_proposal_with_boundaries


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


def test_unresolved_existing_coordinate_becomes_boundary_evidence():
    proposal = {
        "canonical_id": "parks:little-bay",
        "title": "Silent Disco On The Bay",
        "date": "2026-07-24",
        "location": "Little Bay Park",
        "disposition": "unresolved",
        "existing_latitude": 40.7896,
        "existing_longitude": -73.7870,
        "proposed_borough": None,
    }
    boundaries = [("Queens", square(-73.80, 40.78, -73.77, 40.81))]
    evidence = evidence_from_proposal_with_boundaries(proposal, boundaries)
    assert evidence is not None
    assert evidence["borough"] == "Queens"
    assert evidence["source_kind"] == "review_existing_coordinate_dcp_boundary_evidence"


def test_boundary_conflict_rejects_existing_coordinate_evidence():
    proposal = {
        "canonical_id": "test:conflict",
        "title": "Test",
        "date": "2026-07-24",
        "location": "Test Place",
        "disposition": "unresolved",
        "existing_latitude": 40.7896,
        "existing_longitude": -73.7870,
        "proposed_borough": "Brooklyn",
    }
    boundaries = [("Queens", square(-73.80, 40.78, -73.77, 40.81))]
    assert evidence_from_proposal_with_boundaries(proposal, boundaries) is None
