import pytest

from scripts import official_event_contract as contract
from scripts import supabase_event_writer as writer
from scripts import sync_supabase_official_source_catchup as catchup


def test_tvpp_and_feast_pin_only_with_resolver_evidence():
    assert contract.apply_pin_policy("tvpp-9vvx", 40.7, -74.0) == (None, None, False)
    lat, lng, ready = contract.apply_pin_policy(
        "tvpp-9vvx",
        40.7,
        -74.0,
        {"exact_pin_eligible": True, "reason_code": "TVPP_PARKS_FACILITY_OFFICIAL"},
    )
    assert ready is True
    assert lat == 40.7
    assert contract.apply_pin_policy(
        "nyc-projected-feast-reference",
        40.742602,
        -73.876637,
    ) == (None, None, False)
    feast_lat, feast_lng, feast_ready = contract.apply_pin_policy(
        "nyc-projected-feast-reference",
        40.742602,
        -73.876637,
        {"exact_pin_eligible": True, "reason_code": "TVPP_NYC_GEOSEARCH_STREET"},
    )
    assert feast_ready is True
    assert feast_lat == pytest.approx(40.742602)
    assert feast_lng == pytest.approx(-73.876637)


def test_parks_requires_official_evidence():
    assert contract.apply_pin_policy("nyc-parks-bigapps-events", 40.7, -74.0, None)[2] is False
    lat, lng, ready = contract.apply_pin_policy(
        "nyc-parks-bigapps-events",
        40.7,
        -74.0,
        {"exact_pin_eligible": True, "reason_code": "OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED"},
    )
    assert ready is True
    assert lat == 40.7


def test_calendar_pins_only_with_in_bounds_snapshot_coords():
    assert contract.apply_pin_policy("nyc-citywide-events-calendar-api", None, None)[2] is False
    assert contract.apply_pin_policy("nyc-citywide-events-calendar-api", 41.9, -87.6)[2] is False
    lat, lng, ready = contract.apply_pin_policy("nyc-citywide-events-calendar-api", 40.71, -74.01)
    assert ready is True
    assert lat == pytest.approx(40.71)


def test_contract_rejects_map_ready_without_coords():
    row = {
        "occurrence_id": "a" * 64,
        "title": "Bad pin",
        "start_at": "2026-09-04T10:00:00-04:00",
        "timezone": "America/New_York",
        "display_location": "Somewhere",
        "map_ready": True,
        "lat": None,
        "lng": None,
        "status": "active",
        "source_active": True,
        "metadata": {
            "reader": {
                "event_role": "public_event",
                "certified_pin": True,
                "map_eligibility_state": "MAP_READY",
                "display_disposition": "MAP",
                "location_authority": "test",
                "source_dataset": "nyc-parks-bigapps-events",
                "source_event_id": "1",
            }
        },
        "source": {
            "source_name": "nyc_open_data",
            "source_dataset": "nyc-parks-bigapps-events",
            "source_event_id": "1",
            "source_active": True,
        },
    }
    with pytest.raises(contract.OfficialEventContractError):
        contract.assert_rung8_event(row)


def test_all_official_datasets_emit_reader_contract():
    samples = {
        "nyc-parks-bigapps-events": writer.normalize_event(catchup.parks_events()[0]),
        "tvpp-9vvx": writer.normalize_event(catchup.tvpp_events()[0]),
        "nyc-citywide-events-calendar-api": writer.normalize_event(catchup.calendar_events()[0]),
        "nyc-projected-feast-reference": writer.normalize_event(catchup.feast_events()[0]),
    }
    for dataset, row in samples.items():
        contract.apply_reader_display(row)
        contract.assert_rung8_event(row)
        assert row["source"]["source_dataset"] == dataset
        assert row["metadata"]["reader"]["source_dataset"] == dataset
        if dataset in contract.PIN_NEVER:
            assert row["map_ready"] is False
            assert row["lat"] is None
            assert row["lng"] is None


def test_feast_pins_only_with_official_street_evidence():
    events = catchup.feast_events()
    assert events
    for event in events:
        if event.get("map_ready") is True:
            assert event.get("lat") is not None and event.get("lng") is not None
            evidence = ((event.get("source") or {}).get("raw_record") or {}).get("location_evidence")
            assert contract.official_pin_evidence(evidence) is True
        else:
            assert event.get("lat") is None and event.get("lng") is None
    first = writer.normalize_event(events[0])
    checked = contract.assert_official_batch([first], "nyc-projected-feast-reference")
    assert checked[0]["source"]["source_dataset"] == "nyc-projected-feast-reference"
