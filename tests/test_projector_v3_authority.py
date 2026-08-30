from scripts import project_events_discovery_v03 as v3


def exact_evidence():
    return {
        "tier": "exact_address",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": "nyc_geoclient_address",
        "reason_code": "ADDRESS_GEOCLIENT_VALIDATED",
    }


def base_row(**extra):
    row = {
        "source_dataset": "tvpp-9vvx",
        "source_event_id": "evt-1",
        "event_name": "Public Test Event",
        "title": "Public Test Event",
        "event_borough": "Manhattan",
        "borough": "Manhattan",
        "event_location": "1 Centre Street",
        "location": "1 Centre Street",
        "start_date_time": "2026-08-08T10:00:00",
        "end_date_time": "2026-08-08T12:00:00",
    }
    row.update(extra)
    return row


def build(row, index=1):
    return v3.v3_build_base_event(
        row,
        data_layer="approved_staged",
        index=index,
        production_feed=True,
        current_major_keys=set(),
    )


def test_v3_strips_legacy_coordinates_without_evidence():
    event = v3.v3_build_base_event(
        base_row(lat=40.7128, lng=-74.0060),
        data_layer="review_supplemental",
        index=1,
        production_feed=False,
        current_major_keys=set(),
    )
    assert event is not None
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["address"] is None
    assert event["nycif"]["certified_pin"] is False
    assert event["nycif"]["display_disposition"] == "list_only"


def test_v3_preserves_exact_source_location_when_geometry_is_withheld():
    event = v3.v3_build_base_event(
        base_row(
            event_location="Marine Park: Lawn (Fillmore Avenue)",
            location="Brooklyn",
            lat=None,
            lng=None,
        ),
        data_layer="review_supplemental",
        index=7,
        production_feed=False,
        current_major_keys=set(),
    )
    assert event is not None
    assert event["location"] == "Marine Park: Lawn (Fillmore Avenue)"
    assert event["nycif"]["source_location_text"] == "Marine Park: Lawn (Fillmore Avenue)"
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["nycif"]["certified_pin"] is False


def test_v3_validated_exact_public_event_controls_pin_and_disposition():
    event = build(base_row(lat=40.7128, lng=-74.0060, location_evidence=exact_evidence()), index=2)
    assert event is not None
    assert event["event_role"] == "public_event"
    assert event["latitude"] == 40.7128
    assert event["longitude"] == -74.0060
    assert event["nycif"]["map_eligibility_state"] == "MAP_READY"
    assert event["nycif"]["certified_pin"] is True
    assert event["nycif"]["display_disposition"] == "standalone_public_event"


def test_v3_non_public_event_cannot_be_map_ready_even_with_exact_evidence(monkeypatch):
    original = v3._ORIGINAL_BUILD_BASE_EVENT

    def fake_build(row, **kwargs):
        event = original(row, **kwargs)
        assert event is not None
        event["event_role"] = "supporting_permit"
        event["nycif"]["display_disposition"] = "grouped_under_public_event"
        return event

    monkeypatch.setattr(v3, "_ORIGINAL_BUILD_BASE_EVENT", fake_build)
    event = build(base_row(lat=40.7128, lng=-74.0060, location_evidence=exact_evidence()), index=3)
    assert event is not None
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["nycif"]["map_eligibility_state"] == "LIST_ONLY"
    assert event["nycif"]["certified_pin"] is False
    assert event["nycif"]["display_disposition"] == "grouped_under_public_event"


def test_v3_child_event_cannot_be_map_ready(monkeypatch):
    original = v3._ORIGINAL_BUILD_BASE_EVENT

    def fake_build(row, **kwargs):
        event = original(row, **kwargs)
        assert event is not None
        event["event_role"] = "public_event"
        event["parent_event_id"] = "parent-1"
        event["nycif"]["display_disposition"] = "grouped_under_public_event"
        return event

    monkeypatch.setattr(v3, "_ORIGINAL_BUILD_BASE_EVENT", fake_build)
    event = build(base_row(lat=40.7128, lng=-74.0060, location_evidence=exact_evidence()), index=4)
    assert event is not None
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["nycif"]["map_eligibility_state"] == "LIST_ONLY"
    assert event["nycif"]["certified_pin"] is False


def test_v3_non_standalone_public_event_cannot_be_map_ready(monkeypatch):
    original = v3._ORIGINAL_BUILD_BASE_EVENT

    def fake_build(row, **kwargs):
        event = original(row, **kwargs)
        assert event is not None
        event["event_role"] = "public_event"
        event["nycif"]["display_disposition"] = "maintenance_or_closure"
        return event

    monkeypatch.setattr(v3, "_ORIGINAL_BUILD_BASE_EVENT", fake_build)
    event = build(base_row(lat=40.7128, lng=-74.0060, location_evidence=exact_evidence()), index=5)
    assert event is not None
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["nycif"]["map_eligibility_state"] == "LIST_ONLY"
    assert event["nycif"]["certified_pin"] is False


def test_unverified_exact_address_remains_review_required():
    evidence = exact_evidence()
    evidence["source_provenance"] = "nyc_geosearch_planninglabs"
    evidence["reason_code"] = "address_and_borough_validated"
    event = build(base_row(lat=40.7128, lng=-74.0060, location_evidence=evidence), index=6)
    assert event is not None
    assert event["latitude"] is None
    assert event["longitude"] is None
    assert event["nycif"]["map_eligibility_state"] == "REVIEW_REQUIRED"
    assert event["nycif"]["certified_pin"] is False


def test_scoped_rejection_supports_exact_and_day_without_source_widening():
    rejects = v3.ScopedRejectedOccurrences(
        {("tvpp-9vvx", "evt-1", "2026-08-08T10:00:00")},
        {("tvpp-9vvx", "evt-2", "2026-08-09")},
    )
    assert ("tvpp-9vvx", "evt-1", "2026-08-08T10:00:00") in rejects
    assert ("tvpp-9vvx", "evt-2", "2026-08-09T14:00:00") in rejects
    assert ("tvpp-9vvx", "evt-2", "2026-08-10T14:00:00") not in rejects
    assert ("tvpp-9vvx", "evt-3", "2026-08-09T14:00:00") not in rejects
