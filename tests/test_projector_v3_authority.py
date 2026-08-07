from scripts import project_events_discovery_v03 as v3


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


def test_v3_validated_exact_evidence_controls_pin_and_disposition():
    event = v3.v3_build_base_event(
        base_row(
            lat=40.7128,
            lng=-74.0060,
            location_evidence={
                "tier": "exact_address",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "nyc_geosearch",
            },
        ),
        data_layer="approved_staged",
        index=2,
        production_feed=True,
        current_major_keys=set(),
    )
    assert event is not None
    assert event["latitude"] == 40.7128
    assert event["longitude"] == -74.0060
    assert event["nycif"]["map_eligibility_state"] == "MAP_READY"
    assert event["nycif"]["certified_pin"] is True
    assert event["nycif"]["display_disposition"] == "standalone_public_event"


def test_scoped_rejection_supports_exact_and_day_without_source_widening():
    rejects = v3.ScopedRejectedOccurrences(
        {("tvpp-9vvx", "evt-1", "2026-08-08T10:00:00")},
        {("tvpp-9vvx", "evt-2", "2026-08-09")},
    )
    assert ("tvpp-9vvx", "evt-1", "2026-08-08T10:00:00") in rejects
    assert ("tvpp-9vvx", "evt-2", "2026-08-09T14:00:00") in rejects
    assert ("tvpp-9vvx", "evt-2", "2026-08-10T14:00:00") not in rejects
    assert ("tvpp-9vvx", "evt-3", "2026-08-09T14:00:00") not in rejects
