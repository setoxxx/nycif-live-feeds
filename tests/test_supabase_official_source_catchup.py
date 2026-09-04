import json
from pathlib import Path

import pytest

from scripts import supabase_event_writer as writer
from scripts import sync_supabase_official_source_catchup as catchup


def test_parks_official_coordinate_certifies_and_keeps_enigma_id():
    events = catchup.parks_events()
    schmul = next(event for event in events if event["source"]["source_event_id"] == "2223183")
    assert schmul["map_ready"] is True
    assert schmul["lat"] == pytest.approx(40.590108078298)
    assert schmul["lng"] == pytest.approx(-74.188181161881)
    assert schmul["metadata"]["reader"]["certified_pin"] is True
    normalized = writer.normalize_event(schmul)
    assert normalized["occurrence_id"] == "00acee08d465ac58c74ee7a8aff01155c89e24d0ef5cf44fab7fc1555d72eae0"
    assert normalized["map_ready"] is True
    assert normalized["source"]["source_name"] == "nyc_open_data"
    assert normalized["source"]["source_dataset"] == "nyc-parks-bigapps-events"
    assert isinstance(normalized["classification"]["confidence"], (int, float))
    assert float(normalized["classification"]["confidence"]) == 0.95


def test_tvpp_never_becomes_a_map_pin():
    events = catchup.tvpp_events()
    assert events
    assert all(event["map_ready"] is False for event in events)
    assert all(event["lat"] is None and event["lng"] is None for event in events)
    first = writer.normalize_event(events[0])
    assert first["map_ready"] is False
    assert first["source"]["source_dataset"] == "tvpp-9vvx"
    assert len(first["occurrence_id"]) == 64


def test_calendar_labor_day_matches_live_id_and_stays_list_only():
    events = catchup.calendar_events()
    labor = next(event for event in events if event["source"]["source_event_id"] == "10729")
    assert labor["map_ready"] is False
    assert labor["lat"] is None
    normalized = writer.normalize_event(labor)
    assert normalized["occurrence_id"] == "541ec8bcd390fc4f27be5c24c83eaa82fa76815ec7e2065af9c81483b3e2fda8"


def test_parks_without_official_evidence_never_invents_a_pin():
    lat, lng, ready = catchup.official_parks_pin(
        {"lat": 40.7, "lng": -74.0, "location_evidence": None}
    )
    assert (lat, lng, ready) == (None, None, False)
    lat, lng, ready = catchup.official_parks_pin(
        {
            "lat": 40.7,
            "lng": -74.0,
            "location_evidence": {
                "exact_pin_eligible": True,
                "reason_code": "OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED",
            },
        }
    )
    assert ready is True
    assert lat == 40.7


def test_write_chunks_never_allow_expire(monkeypatch):
    captured = {}

    def fake_validate():
        return "oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co"

    def fake_post(target_url, service_key, payload, timeout=120):
        captured["payload"] = payload
        return {"transaction": "committed", "actions": {"INSERT": 1}, "newsroom_queue_delta": 0, "pipeline_run_id": 1}

    monkeypatch.setattr(catchup.writer, "validate_write_target", fake_validate)
    monkeypatch.setattr(catchup.writer, "post_atomic_batch", fake_post)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    result = catchup.write_chunks(
        [
            {
                "occurrence_id": "a" * 64,
                "title": "Demo",
                "source": {"source_name": "nyc_open_data"},
                "map_ready": False,
            }
        ],
        10,
    )
    assert captured["payload"]["p_allow_expire"] is False
    assert captured["payload"]["p_source_name"] == "nyc_open_data"
    assert result["actions"]["INSERT"] == 1


def test_discovery_refresh_still_does_not_write_events():
    workflow = Path(".github/workflows/discovery-feed-refresh.yml").read_text(encoding="utf-8")
    assert "sync_supabase_official_source_catchup.py" not in workflow
    assert "supabase_event_writer.py" not in workflow
    assert "nycif_apply_staging_event_batch" not in workflow


def test_catchup_workflow_is_separate_and_fail_closed():
    workflow = Path(".github/workflows/supabase-official-source-catchup.yml").read_text(encoding="utf-8")
    assert "sync_supabase_official_source_catchup.py" in workflow
    assert "SUPABASE_WRITE_ENABLED" in workflow
    assert "p_allow_expire" not in workflow or "--write" in workflow
    assert "location_cache.json" not in workflow
    assert "nycif_staged_live_events.json" not in workflow
