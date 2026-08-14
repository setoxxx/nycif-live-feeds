from scripts.projector_v2_authority import (
    build_rejection_contract,
    classify_occurrence_intake,
    occurrence_identity_v2,
    occurrence_identity_v2_set,
    rejection_applies,
    semantic_map_decision,
)


SEASON_START = "2026-07-14"
SEASON_END = "2026-12-27"


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
            "site_validation_state": "validated",
            "exact_pin_eligible": True,
            "source_provenance": "fixture",
            "reason_code": "SOURCE_COORDINATE_SITE_VALIDATED",
        },
    }


def classify(row, represented=(), rejected=()):
    return classify_occurrence_intake(
        row,
        represented_occurrences=set(represented),
        rejection_contract=build_rejection_contract(list(rejected)),
        season_start=SEASON_START,
        season_end=SEASON_END,
    )


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
    assert result["exact_site_validated"] is True
    assert result["latitude"] == 40.7128
    assert result["longitude"] == -74.0060


def test_source_coordinate_without_site_validation_is_not_map_ready():
    row = exact_row()
    row["location_evidence"] = dict(row["location_evidence"])
    row["location_evidence"].pop("site_validation_state")
    row["location_evidence"]["reason_code"] = "OFFICIAL_SOURCE_COORDINATE"
    result = semantic_map_decision(row)
    assert result["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert result["certified_pin"] is False
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["reason_code"] == "SOURCE_COORDINATE_SITE_UNVERIFIED"


def test_legacy_geosearch_midpoint_tier_cannot_publish_exact_geometry():
    row = exact_row()
    row["location_evidence"] = {
        "tier": "tier_2_geosearch_midpoint",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": "nyc_geosearch_planninglabs_midpoint",
        "reason_code": "SEGMENT_ENDPOINTS_VALIDATED",
    }
    result = semantic_map_decision(row)
    assert result["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert result["certified_pin"] is False
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["reason_code"] == "LEGACY_EXACT_TIER_PROHIBITED"


def test_exact_address_requires_site_validation():
    row = exact_row()
    row["location_evidence"] = {
        "tier": "exact_address",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": "nyc_geoclient_address",
        "reason_code": "ADDRESS_GEOCLIENT_VALIDATED",
    }
    result = semantic_map_decision(row)
    assert result["map_eligibility_state"] == "MAP_READY"
    assert result["certified_pin"] is True


def test_intake_exact_duplicate_is_documented_duplicate():
    row = exact_row()
    represented = occurrence_identity_v2_set([row])
    assert classify(row, represented=represented) == "documented_duplicate"


def test_intake_same_day_sibling_is_not_duplicate():
    represented = occurrence_identity_v2_set([exact_row("2026-08-07T10:00:00-04:00")])
    sibling = exact_row("2026-08-07T11:00:00-04:00")
    assert classify(sibling, represented=represented) == "accepted_review_supplemental"


def test_intake_exact_rejection_class_is_explicit():
    row = exact_row("2026-08-07T10:00:00-04:00")
    rejected = row | {"disposition": "rejected", "rejection_scope": "EXACT_START"}
    assert classify(row, rejected=[rejected]) == "rejected_exact"


def test_intake_day_rejection_class_is_explicit():
    row = exact_row("2026-08-07T10:00:00-04:00")
    rejected = {
        "source_dataset": "test",
        "source_event_id": "evt-1",
        "date": "2026-08-07",
        "disposition": "rejected",
        "rejection_scope": "DAY",
    }
    assert classify(row, rejected=[rejected]) == "rejected_day"
    assert classify(exact_row("2026-08-08T10:00:00-04:00"), rejected=[rejected]) == "accepted_review_supplemental"


def test_intake_source_all_class_requires_explicit_scope():
    rejected = {
        "source_dataset": "test",
        "source_event_id": "evt-1",
        "disposition": "rejected",
        "rejection_scope": "SOURCE_ALL_OCCURRENCES",
    }
    assert classify(exact_row(), rejected=[rejected]) == "rejected_source_all"


def test_intake_ambiguous_row_is_preserved_for_review():
    row = {"source_dataset": "test", "source_event_id": "evt-2"}
    assert classify(row) == "outside_window"


def test_intake_ambiguous_in_window_row_is_review_not_source_wide():
    row = {
        "source_dataset": "test",
        "source_event_id": "evt-2",
        "start_date_time": "2026-08-07",
    }
    assert occurrence_identity_v2(row)["precision"] == "DAY"
    assert classify(row) == "accepted_review_supplemental"


def test_intake_outside_window_is_explicit():
    assert classify(exact_row("2027-01-10T10:00:00-05:00")) == "outside_window"
