import json
from datetime import timedelta
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


def test_tvpp_public_events_pin_from_official_sources():
    events = catchup.tvpp_events()
    assert events
    assert all(event["map_ready"] is True for event in events)
    assert all(event["lat"] is not None and event["lng"] is not None for event in events)
    first = writer.normalize_event(events[0])
    assert first["map_ready"] is True
    assert first["source"]["source_dataset"] == "tvpp-9vvx"
    assert first["metadata"]["reader"]["certified_pin"] is True
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
    assert "--from-batch" in workflow
    assert "supabase_official_today_listing.json" in workflow
    assert "supabase_official_event_batch.json" in workflow
    assert "github.event_name == 'workflow_run' && 'main'" in workflow
    assert "nyc-projected-feast-reference" in workflow
    assert "projected feast rows must stay accounted as pin or list-only" in workflow
    assert "tvpp street permits must all be pinned" in workflow
    assert "official_daily_machine.py" in workflow
    assert "official_daily_machine_report.json" in workflow
    assert "official daily machine failed" in workflow


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
    assert catchup.BATCH_PATH.name == catchup.BATCH_FILENAME
    assert catchup.TODAY_LISTING_PATH.name == catchup.TODAY_LISTING_FILENAME
    assert catchup.BATCH_PATH.parent == catchup.REPORTS_DIR
    assert catchup.TODAY_LISTING_PATH.parent == catchup.REPORTS_DIR


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


def test_tvpp_skips_operational_permits_and_pins_public_events():
    rejections: list[dict] = []
    events = catchup.tvpp_events(rejections=rejections)
    assert events
    assert all(event["metadata"]["reader"]["event_role"] == "public_event" for event in events)
    assert all(event["map_ready"] is True for event in events)
    assert all(event["lat"] is not None and event["lng"] is not None for event in events)
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


def _sample_row(*, occurrence_id: str, title: str, start_at: str, end_at: str, dataset: str, map_ready: bool = False):
    return {
        "occurrence_id": occurrence_id,
        "title": title,
        "start_at": start_at,
        "end_at": end_at,
        "timezone": "America/New_York",
        "borough": "Brooklyn",
        "display_location": "A park",
        "lat": 40.7 if map_ready else None,
        "lng": -74.0 if map_ready else None,
        "map_ready": map_ready,
        "public_category": "parks",
        "public_subtype": None,
        "editorial_priority": "normal",
        "metadata": {
            "reader": {
                "event_role": "public_event",
                "certified_pin": map_ready,
                "map_eligibility_state": "MAP_READY" if map_ready else "LIST_ONLY",
                "display_disposition": "MAP" if map_ready else "LIST_ONLY",
                "location_authority": "test",
                "source_dataset": dataset,
                "source_event_id": "1",
                "public_url": None,
                "is_major": False,
                "photo_pick": False,
                "significance": "standard",
            }
        },
        "source": {
            "source_name": "nyc_open_data",
            "source_dataset": dataset,
            "source_event_id": "1",
            "source_url": None,
        },
    }


def test_today_listing_uses_reader_overlap_window_not_start_date_only():
    today = catchup.today_nyc()
    yesterday = (catchup.ny_day_bounds(today)[0] - timedelta(days=1)).date().isoformat()
    tomorrow = (catchup.ny_day_bounds(today)[1]).date().isoformat()
    started_yesterday = _sample_row(
        occurrence_id="a" * 64,
        title="Still going",
        start_at=catchup._ny_timestamptz(f"{yesterday}T22:00:00"),
        end_at=catchup._ny_timestamptz(f"{today}T02:00:00"),
        dataset="tvpp-9vvx",
    )
    starts_today = _sample_row(
        occurrence_id="b" * 64,
        title="Starts today",
        start_at=catchup._ny_timestamptz(f"{today}T09:00:00"),
        end_at=catchup._ny_timestamptz(f"{today}T11:00:00"),
        dataset="nyc-parks-bigapps-events",
        map_ready=True,
    )
    starts_tomorrow = _sample_row(
        occurrence_id="c" * 64,
        title="Tomorrow only",
        start_at=catchup._ny_timestamptz(f"{tomorrow}T09:00:00"),
        end_at=catchup._ny_timestamptz(f"{tomorrow}T11:00:00"),
        dataset="nyc-parks-bigapps-events",
        map_ready=True,
    )
    listing = catchup.today_listing_events([started_yesterday, starts_today, starts_tomorrow], today)
    assert {row["title"] for row in listing} == {"Still going", "Starts today"}
    pin = next(row for row in listing if row["title"] == "Starts today")
    assert pin["map_ready"] is True
    assert pin["certified_pin"] is True
    assert pin["source_dataset"] == "nyc-parks-bigapps-events"
    street = next(row for row in listing if row["title"] == "Still going")
    assert street["map_ready"] is False
    assert street["lat"] is None
    assert street["source_dataset"] == "tvpp-9vvx"


def test_exported_json_matches_rung8_and_reader_contracts(tmp_path, monkeypatch):
    monkeypatch.setattr(catchup, "REPORTS_DIR", tmp_path)
    today = "2026-09-04"
    parks = _sample_row(
        occurrence_id="d" * 64,
        title="Park pin",
        start_at=catchup._ny_timestamptz("2026-09-04T10:00:00"),
        end_at=catchup._ny_timestamptz("2026-09-04T12:00:00"),
        dataset="nyc-parks-bigapps-events",
        map_ready=True,
    )
    tvpp = _sample_row(
        occurrence_id="e" * 64,
        title="Street permit",
        start_at=catchup._ny_timestamptz("2026-09-04T10:00:00"),
        end_at=catchup._ny_timestamptz("2026-09-04T14:00:00"),
        dataset="tvpp-9vvx",
    )
    batch_path, listing_path, listing = catchup.export_official_payloads(
        {"nyc-parks-bigapps-events": [parks], "tvpp-9vvx": [tvpp]},
        today=today,
    )
    batch = json.loads(batch_path.read_text())
    loaded = catchup.load_official_batch(batch_path)
    assert loaded["schema"] == catchup.BATCH_SCHEMA
    assert loaded["p_allow_expire"] is False
    assert loaded["p_source_name"] == "nyc_open_data"
    assert loaded["p_expected_project_ref"] == "oggwpvdirkrnzoolparx"
    assert batch["datasets"]["tvpp-9vvx"]["p_events"][0]["map_ready"] is False
    assert listing["schema"] == catchup.TODAY_LISTING_SCHEMA
    assert listing["today_nyc"] == today
    assert listing["rows"] == 2
    assert listing["map_ready"] == 1
    assert listing["by_dataset"]["tvpp-9vvx"]["map_ready"] == 0
    assert json.loads(listing_path.read_text())["events"][0]["source_dataset"]
    for event in listing["events"]:
        for key in (
            "occurrence_id",
            "title",
            "start_at",
            "map_ready",
            "certified_pin",
            "map_eligibility_state",
            "event_role",
            "source_dataset",
            "source_event_id",
        ):
            assert key in event


def test_write_from_batch_posts_file_events(monkeypatch, tmp_path):
    monkeypatch.setattr(catchup, "REPORTS_DIR", tmp_path)
    captured = []

    def fake_validate():
        return "oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co"

    def fake_post(target_url, service_key, payload, timeout=120):
        captured.append(payload)
        return {"transaction": "committed", "actions": {"INSERT": 1}, "newsroom_queue_delta": 0, "pipeline_run_id": 3}

    monkeypatch.setattr(catchup.writer, "validate_write_target", fake_validate)
    monkeypatch.setattr(catchup.writer, "post_atomic_batch", fake_post)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    row = _sample_row(
        occurrence_id="f" * 64,
        title="From file",
        start_at=catchup._ny_timestamptz("2026-09-04T10:00:00"),
        end_at=catchup._ny_timestamptz("2026-09-04T12:00:00"),
        dataset="nyc-citywide-events-calendar-api",
    )
    batch_path, _, _ = catchup.export_official_payloads(
        {"nyc-citywide-events-calendar-api": [row]},
        today="2026-09-04",
    )
    result = catchup.write_official_batch(catchup.load_official_batch(batch_path), 10)
    assert captured[0]["p_events"][0]["occurrence_id"] == "f" * 64
    assert captured[0]["p_allow_expire"] is False
    assert result["nyc-citywide-events-calendar-api"]["actions"]["INSERT"] == 1


def test_parks_today_listing_keeps_schmul_pin_fields():
    events = [writer.normalize_event(event) for event in catchup.parks_events()]
    schmul = next(event for event in events if event["source"]["source_event_id"] == "2223183")
    listing_row = catchup.reader_listing_row(schmul)
    assert listing_row["source_dataset"] == "nyc-parks-bigapps-events"
    assert listing_row["map_ready"] is True
    assert listing_row["certified_pin"] is True
    assert listing_row["lat"] == pytest.approx(40.590108078298)
    assert listing_row["occurrence_id"] == "00acee08d465ac58c74ee7a8aff01155c89e24d0ef5cf44fab7fc1555d72eae0"
