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
    assert "The phone reads Supabase" in workflow
    assert "pip install" not in workflow
    assert "requirements.txt" not in workflow
    assert "cron:" not in workflow
    assert "workflow_run:" in workflow


def test_finite_coord_rejects_nan_and_inf():
    assert catchup._finite_coord("40.7") == pytest.approx(40.7)
    assert catchup._finite_coord("not-a-number") is None
    assert catchup._finite_coord(float("nan")) is None
    assert catchup._finite_coord(float("inf")) is None
    assert catchup._finite_coord(float("-inf")) is None


def test_catchup_report_stays_inside_data_reports():
    assert catchup.REPORT_PATH == catchup.ROOT / "data" / "reports" / "supabase_official_source_catchup_report.json"
    assert catchup.REPORT_PATH.parent == catchup.REPORTS_DIR
    assert catchup.REPORT_PATH.name == catchup.REPORT_FILENAME


def test_naive_new_york_times_get_an_offset_without_changing_parks_ids():
    stamp = catchup._ny_timestamptz("2026-09-03T07:00:00")
    assert stamp is not None
    assert stamp.startswith("2026-09-03T07:00:00")
    assert "-04:00" in stamp or "-05:00" in stamp
    events = catchup.parks_events()
    schmul = next(event for event in events if event["source"]["source_event_id"] == "2223183")
    normalized = writer.normalize_event(schmul)
    assert normalized["occurrence_id"] == "00acee08d465ac58c74ee7a8aff01155c89e24d0ef5cf44fab7fc1555d72eae0"
    assert normalized["start_at"].endswith("-04:00") or normalized["start_at"].endswith("-05:00")


def test_invalid_intervals_are_rejected_and_reported():
    rejections: list[dict] = []
    catchup._note_rejection(
        rejections,
        dataset="nyc-parks-bigapps-events",
        source_event_id="1",
        title="Bad",
        reason="invalid_interval",
    )
    assert catchup._valid_interval("2026-09-03T12:00:00", "2026-09-03T11:00:00") is False
    assert catchup._valid_interval("2026-09-03T11:00:00", "2026-09-03T12:00:00") is True
    parks_rejections: list[dict] = []
    catchup.parks_events(rejections=parks_rejections)
    inverted = [item for item in parks_rejections if item["reason"] == "invalid_interval"]
    assert inverted


def test_tvpp_skips_operational_permits_and_stays_list_only():
    rejections: list[dict] = []
    events = catchup.tvpp_events(rejections=rejections)
    assert events
    assert all(event["map_ready"] is False for event in events)
    assert all(event["metadata"]["reader"]["event_role"] == "public_event" for event in events)
    titles = {event["title"] for event in events}
    assert "Closure" not in titles
    assert any("not_public_event" in item["reason"] or item["reason"] == "invalid_interval" for item in rejections)


def test_calendar_normalizes_borough_codes_and_keeps_labor_day_id():
    events = catchup.calendar_events()
    labor = next(event for event in events if event["source"]["source_event_id"] == "10729")
    assert labor["borough"] == "Citywide"
    normalized = writer.normalize_event(labor)
    assert normalized["occurrence_id"] == "541ec8bcd390fc4f27be5c24c83eaa82fa76815ec7e2065af9c81483b3e2fda8"
    assert catchup._borough(["Mn", "Bk", "Qn", "Bx", "SI"]) == "Citywide"
    assert catchup._borough("Bk") == "Brooklyn"


def test_write_chunks_records_partial_progress_on_failure(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_validate():
        return "oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co"

    def fake_post(target_url, service_key, payload, timeout=120):
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("boom")
        return {"transaction": "committed", "actions": {"INSERT": 1}, "newsroom_queue_delta": 0, "pipeline_run_id": 9}

    monkeypatch.setattr(catchup.writer, "validate_write_target", fake_validate)
    monkeypatch.setattr(catchup.writer, "post_atomic_batch", fake_post)
    monkeypatch.setattr(catchup, "REPORTS_DIR", tmp_path)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    rows = [
        {
            "occurrence_id": f"{index:064x}",
            "title": f"Row {index}",
            "source": {"source_name": "nyc_open_data"},
            "map_ready": False,
        }
        for index in range(11)
    ]
    progress = {"database_write_performed": False, "datasets": {}}
    with pytest.raises(RuntimeError, match="boom"):
        catchup.write_chunks(rows, 10, progress=progress)
    assert progress["database_write_performed"] is True
    assert progress["chunks_committed"] == 1
    assert (tmp_path / catchup.REPORT_FILENAME).exists()
