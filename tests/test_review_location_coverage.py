from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_review_location_coverage import (
    build_spatial_index,
    load_review_events,
    resolve_null_borough_event,
)
from scripts.nyc_location_gazetteer import NYCLocationGazetteer


def event(**overrides):
    payload = {
        "id": "review:test:1@2026-07-28",
        "title": "Test event",
        "borough": None,
        "location": "Test Place",
        "latitude": None,
        "longitude": None,
        "source": {
            "dataset": "test",
            "source_event_id": "1",
            "source_url": "https://example.invalid/event/1",
        },
        "nycif": {"event_date": "2026-07-28"},
    }
    payload.update(overrides)
    return payload


def gazetteer(entries=None):
    return NYCLocationGazetteer(entries or {})


def test_online_event_is_classified_without_pin():
    g = gazetteer()
    result = resolve_null_borough_event(
        event(location="Virtual/Online Events"),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "online"
    assert result["location_classified"] is True
    assert result["pin_eligible"] is False


def test_citywide_event_is_classified_without_fake_pin():
    g = gazetteer()
    result = resolve_null_borough_event(
        event(location="Locations across all five boroughs"),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "citywide_or_multi_location"
    assert result["pin_eligible"] is False


def test_existing_coordinates_use_unique_borough_name():
    g = gazetteer()
    result = resolve_null_borough_event(
        event(
            location="Prospect Park, Brooklyn",
            latitude=40.6602,
            longitude=-73.9690,
        ),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "borough_normalized_existing_coordinates"
    assert result["proposed_borough"] == "Brooklyn"
    assert result["proposed_latitude"] == 40.6602
    assert result["pin_eligible"] is True


def test_existing_coordinates_use_nearby_borough_evidence():
    g = gazetteer(
        {
            "prospect park": {
                "lat": 40.6602,
                "lng": -73.9690,
                "borough": "Brooklyn",
                "label": "Prospect Park",
                "source": "test_reference",
                "confidence": "high",
            }
        }
    )
    result = resolve_null_borough_event(
        event(
            location="Unknown lawn",
            latitude=40.66021,
            longitude=-73.96901,
        ),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "borough_normalized_existing_coordinates"
    assert result["proposed_borough"] == "Brooklyn"
    assert result["evidence_distance_m"] < 10


def test_gazetteer_maps_physical_location_without_coordinates():
    g = gazetteer(
        {
            "brooklyn museum": {
                "lat": 40.6712,
                "lng": -73.9636,
                "borough": "Brooklyn",
                "label": "Brooklyn Museum",
                "source": "test_reference",
                "confidence": "high",
                "confidence_reason": "Known facility reference.",
            }
        }
    )
    result = resolve_null_borough_event(
        event(location="Brooklyn Museum"),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "mapped_from_gazetteer"
    assert result["proposed_borough"] == "Brooklyn"
    assert result["proposed_latitude"] == 40.6712
    assert result["pin_eligible"] is True


def test_unresolved_record_still_has_explicit_disposition():
    g = gazetteer()
    result = resolve_null_borough_event(
        event(location="Location to be announced"),
        gazetteer=g,
        spatial_index=build_spatial_index(g),
    )
    assert result["disposition"] == "unresolved"
    assert result["location_classified"] is True
    assert result["pin_eligible"] is False
    assert result["reason"]


def test_manifest_page_loader_is_fail_closed(tmp_path: Path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "page-0001.json").write_text(
        json.dumps({"events": [event()]}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"total": 1, "pages": [{"page": "page-0001.json"}]}),
        encoding="utf-8",
    )
    payload, rows = load_review_events(manifest, pages)
    assert payload["total"] == 1
    assert len(rows) == 1
