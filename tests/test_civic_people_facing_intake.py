"""Fixture tests for civic people-facing date/time/location hardening."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import (  # noqa: E402
    combine_local_datetime,
    date_window_status,
    parse_clock_time,
    parse_iso_date,
    resolve_coordinate_status,
    safety_fields,
)
from schema_v1_common import valid_nyc_coords  # noqa: E402
import build_civic_people_facing_staging as build  # noqa: E402


def test_nyc_validator_rejects_out_of_bounds():
    lat, lng, ok = valid_nyc_coords(39.0, -74.0)
    assert not ok and lat is None and lng is None
    lat, lng, ok = valid_nyc_coords(40.75, -73.98)
    assert ok and lat == pytest.approx(40.75)


def test_coordinate_status_map_ready_and_list_only():
    lat, lng, status, reason = resolve_coordinate_status(40.75, -73.98)
    assert status == "map_ready" and lat is not None
    lat, lng, status, reason = resolve_coordinate_status(None, None)
    assert status == "list_only" and lat is None
    # Fail-closed pin integrity reason (status remains list_only; coords cleared).
    assert reason.startswith("pin_integrity:") or "list_only" in reason


def test_no_invented_times_when_clock_missing():
    assert parse_clock_time("") is None
    assert parse_clock_time(None) is None
    day = date(2026, 7, 20)
    assert combine_local_datetime(day, None) == "2026-07-20T00:00:00"
    assert parse_clock_time("11:30 AM") == (11, 30, 0)
    assert combine_local_datetime(day, (11, 30, 0)) == "2026-07-20T11:30:00"


def test_human_and_iso_date_parsing():
    assert parse_iso_date("Tuesday, March 17, 2020") == date(2020, 3, 17)
    assert parse_iso_date("2026-07-14T14:00:00.000") == date(2026, 7, 14)


def test_past_and_far_future_quarantine():
    today = date(2026, 7, 14)
    assert date_window_status(date(2020, 3, 17), today=today) == "past_date_quarantine"
    assert date_window_status(date(2029, 1, 31), today=today) == "far_future_outlier_quarantine"
    assert date_window_status(date(2026, 7, 20), today=today) is None


def test_safety_fields_fail_closed():
    s = safety_fields()
    assert s["promotion_allowed"] is False
    assert s["manual_review_status"] == "pending"
    assert s["public_map_modified"] is False
    assert s["location_cache_modified"] is False
    assert s["staged_feed_modified"] is False


def test_fixture_workforce1_and_market_normalizers(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(build, "DATA_DIR", data_dir)

    (data_dir / "civic_workforce1_events_snapshot.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "event_title": "Hiring Event",
                        "event_date": "Tuesday, July 21, 2026",
                        "check_in_from": "10:00 AM",
                        "check_in_to": "10:30 AM",
                        "borough": "Bronx",
                        "location": "Bronx Workforce1",
                        "location_name_and_address": "400 East Fordham Road",
                    },
                    {
                        "event_title": "Old Event",
                        "event_date": "Tuesday, March 17, 2020",
                        "borough": "Bronx",
                        "location": "Old",
                        "location_name_and_address": "Old",
                    },
                ]
            }
        )
    )
    (data_dir / "civic_farmers_markets_snapshot.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "year": "2025",
                        "marketname": "Fixture Market",
                        "borough": "Manhattan",
                        "streetaddress": "W 100 St",
                        "latitude": "40.795",
                        "longitude": "-73.96",
                        "daysoperation": "Saturday",
                        "hoursoperations": "8 a.m. - 2 p.m.",
                    },
                    {
                        "year": "2025",
                        "marketname": "Bogus Abroad",
                        "borough": "Manhattan",
                        "streetaddress": "Nowhere",
                        "latitude": "48.85",
                        "longitude": "2.35",
                        "daysoperation": "Monday",
                        "hoursoperations": "9-5",
                    },
                ]
            }
        )
    )

    today = date(2026, 7, 14)
    accepted, quarantined = build.normalize_workforce1_events(today)
    assert any(r["title"] == "Hiring Event" for r in accepted)
    assert any(r["title"] == "Old Event" for r in quarantined)
    hire = next(r for r in accepted if r["title"] == "Hiring Event")
    assert hire["start_date_time"] == "2026-07-21T10:00:00"
    assert hire["promotion_allowed"] is False
    assert hire["coordinate_status"] == "list_only"

    markets = build.normalize_farmers_markets()
    market = next(r for r in markets if r["title"] == "Fixture Market")
    abroad = next(r for r in markets if r["title"] == "Bogus Abroad")
    assert market["coordinate_status"] == "map_ready"
    assert market["start_date_time"] is None
    assert market["schedule_text"]
    assert abroad["coordinate_status"] == "list_only"
    assert abroad["latitude"] is None


def test_committed_qa_reports_pass_when_present():
    qa_path = ROOT / "data" / "civic_people_facing_date_time_location_qa.json"
    if not qa_path.exists():
        pytest.skip("staging artifacts not generated in this checkout")
    qa = json.loads(qa_path.read_text())
    assert qa.get("qa_pass") is True
    assert qa.get("all_promotion_allowed_false") is True
    assert qa.get("no_invented_times") is True
    continuity = json.loads(
        (ROOT / "data" / "civic_people_facing_continuity_report.json").read_text()
    )
    assert continuity.get("upcoming_next_7_days", 0) >= 0
    gap = json.loads((ROOT / "data" / "civic_food_access_gap_note.json").read_text())
    assert gap.get("status") == "known_gap_human_follow_up"


def test_map_coverage_accounts_for_every_accepted_row():
    path = ROOT / "data" / "civic_people_facing_map_coverage_report.json"
    if not path.exists():
        pytest.skip("coverage report not generated")
    report = json.loads(path.read_text())
    assert report.get("qa_pass") is True
    assert report.get("every_accepted_row_classified") is True
    effective = report.get("effective_accounted_with_proposals") or {}
    assert effective.get("equals_accepted") is True
    assert report.get("protected_files", {}).get("location_cache_modified") is False
    proposals = json.loads(
        (ROOT / "data" / "civic_people_facing_geocoding_proposals.json").read_text()
    )
    assert proposals.get("promotion_allowed") is False
    for row in proposals.get("proposals") or []:
        assert row.get("promotion_allowed") is False
        assert row.get("manual_review_status") == "pending"
        assert row.get("coordinate_status") in {"proposed", "list_only"}


def test_civic_godview_digest_bookmarks_project():
    path = ROOT / "data" / "civic_people_facing_godview_digest.json"
    if not path.exists():
        pytest.skip("godview digest not generated")
    digest = json.loads(path.read_text())
    assert digest.get("checkpoint", {}).get("merged_pr") == 171
    assert digest.get("safety", {}).get("promotion_allowed") is False
    assert "feeds=main" in (digest.get("field_desk") or {}).get("preview_after_merge", "")
    panel = (
        ROOT
        / "docs"
        / "field-desk-admin-deploy"
        / "admin"
        / "civic-godview-panel-v01.js"
    )
    assert panel.exists()
    admin = (ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "index.html").read_text()
    assert "civic-godview-panel-v01.js" in admin
    assert "civic-god-view-section" in admin
