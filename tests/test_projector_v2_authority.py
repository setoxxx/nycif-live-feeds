from scripts.projector_v2_authority import (
    build_rejection_contract,
    occurrence_identity_v2,
    rejection_applies,
    semantic_map_decision,
)


def exact_row(start="2026-08-07T10:00:00-04:00"):
    return {
        "source_dataset": "test",
        "source_event_id": "evt-1",
        "start_date_time": start,
        "latitude": 40.7128,
        "longitude": -74.0060,
        "location_evidence": {
            "tier": "exact_source_coordinate",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "source_provenance": "fixture",
        },
    }


def test_same_day_different_exact_start_are_distinct():
    a = exact_row("2026-08-07T10:00:00-04:00")
    b = exact_row("2026-08-07T11:00:00-04:00")
    assert occurrence_identity_v2(a)["key"] != occurrence_identity_v2(b)["key"]


def test_same_exact_start_is_deterministic():
    a = exact_row()
    b = exact_row()
    assert occurrence_identity_v2(a)["key"] == occurrence_identity_v2(b)["key"]


def test_ambiguous_identity_is_preserved():
    row = {"source_dataset": "test", "source_event_id": "evt-2"}
    result = occurrence_identity_v2(row)
    assert result["identity_ambiguous"] is True
    assert result["key"][2] == "identity_ambiguous"


def test_exact_start_rejection_does_not_suppress_sibling():
    rejected = exact_row("2026-08-07T10:00:00-04:00") | {
        "disposition": "rejected",
        "rejection_scope": "EXACT_START",
    }
    contract = build_rejection_contract([rejected])
    assert rejection_applies(exact_row("2026-08-07T10:00:00-04:00"), contract) is True
    assert rejection_applies(exact_row("2026-08-07T11:00:00-04:00"), contract) is False


def test_day_rejection_applies_to_day_only():
    rejected = {
        "source_dataset": "test",
        "source_event_id": "evt-1",
        "date": "2026-08-07",
        "disposition": "rejected",
        "rejection_scope": "DAY",
    }
    contract = build_rejection_contract([rejected])
    assert rejection_applies(exact_row("2026-08-07T10:00:00-04:00"), contract) is True
    assert rejection_applies(exact_row("2026-08-08T10:00:00-04:00"), contract) is False


def test_source_all_requires_explicit_scope():
    rejected = {
        "source_dataset": "test",
        "source_event_id": "evt-1",
        "disposition": "rejected",
        "rejection_scope": "SOURCE_ALL_OCCURRENCES",
    }
    contract = build_rejection_contract([rejected])
    assert rejection_applies(exact_row("2026-08-07T10:00:00-04:00"), contract) is True
    assert rejection_applies(exact_row("2026-08-08T10:00:00-04:00"), contract) is True


def test_coordinates_without_evidence_are_not_exact():
    row = {
        "latitude": 40.7128,
        "longitude": -74.0060,
    }
    result = semantic_map_decision(row)
    assert result["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert result["certified_pin"] is False
    assert result["latitude"] is None
    assert result["longitude"] is None


def test_general_area_strips_exact_coordinates_and_keeps_generalized_label():
    row = {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "general_area_label": "Lower Manhattan",
        "location_evidence": {
            "tier": "approximate_area",
            "validation_state": "validated",
            "exact_pin_eligible": False,
            "source_provenance": "fixture",
        },
    }
    result = semantic_map_decision(row)
    assert result["map_eligibility_state"] == "GENERAL_AREA"
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["general_area_label"] == "Lower Manhattan"


def test_valid_shared_exact_is_map_ready():
    result = semantic_map_decision(exact_row())
    assert result["map_eligibility_state"] == "MAP_READY"
    assert result["certified_pin"] is True
    assert result["latitude"] == 40.7128
    assert result["longitude"] == -74.0060
