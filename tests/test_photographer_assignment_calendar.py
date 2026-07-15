"""Tests for photographer Money-Day Desk v2 calendar + packs."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_photographer_assignment_calendar as cal  # noqa: E402
import build_photographer_money_day_packs as packs  # noqa: E402


def test_score_keeps_parade_excludes_routine_even_with_high_major_score():
    parade = {
        "title": "Puerto Rican Day Parade",
        "category": "civic",
        "significance": "major",
        "nycif": {"is_major": True, "major_score": 450},
    }
    score, rules, excluded = cal.score_row(parade, lane="approved_major")
    assert not excluded
    assert score >= 160
    assert any("civic_gathering" in r or "parade" in r for r in rules)

    softball = {
        "title": "Softball - Adults",
        "category": "market",
        "significance": "major",
        "location": "Parade Ground: Baseball-03",
        "nycif": {"is_major": True, "major_score": 450},
    }
    _, rules2, excluded2 = cal.score_row(softball, lane="approved_major")
    assert excluded2
    assert any(
        r in rules2
        for r in (
            "routine_activity_excluded",
            "no_money_day_keyword_signal",
            "thin_or_non_money_title_excluded",
        )
    )

    yoga = {
        "title": "Chair Yoga Fitness Class",
        "category": "fitness",
        "location": "ZIP 11226",
        "nycif": {"coordinate_status": "list_only", "is_major": True, "major_score": 450},
    }
    _, rules3, excluded3 = cal.score_row(yoga, lane="review_high_signal")
    assert excluded3


def test_location_parade_ground_does_not_create_money_signal():
    row = {
        "title": "Tennis",
        "category": "sports",
        "location": "Parade Ground: Tennis-01",
        "significance": "major",
        "nycif": {"is_major": True, "major_score": 450},
    }
    _, rules, excluded = cal.score_row(row, lane="approved_major")
    assert excluded
    assert "keyword_civic_gathering" not in rules


def test_never_invents_clock_when_missing():
    row = {
        "id": "t1",
        "title": "Street Fair",
        "start_date_time": "2026-08-01T00:00:00.000",
        "location": "Broadway",
        "borough": "Manhattan",
        "latitude": 40.75,
        "longitude": -73.98,
        "source": {"dataset": "tvpp-9vvx", "source_event_id": "1"},
        "nycif": {"event_date": "2026-08-01", "coordinate_status": "map_ready", "is_major": True},
    }
    item = cal.normalize_assignment(row, lane="approved_major", score=200, rules=["keyword_street_fair_festival"])
    assert item["date"] == "2026-08-01"
    assert item["start_date_time"] == "2026-08-01T00:00:00.000"
    assert item["promotion_allowed"] is False
    assert "assignment=1" in item["field_desk_link"]


def test_committed_calendar_and_quality_when_present():
    path = ROOT / "data" / "photographer_assignment_calendar_report.json"
    if not path.exists():
        pytest.skip("calendar not generated yet")
    report = json.loads(path.read_text())
    assert report.get("qa_pass") is True
    assert report.get("total_events", 0) > 0
    assert report.get("total_events") < 842  # quieter than #173 baseline
    assert report.get("protected_files_untouched") is True
    quality = json.loads((ROOT / "data" / "photographer_money_day_quality_report.json").read_text())
    assert quality.get("qa_pass") is True
    assert (quality.get("delta_vs_baseline") or {}).get("events_removed", 0) > 0
    cal_path = ROOT / "data" / "photographer_assignment_calendar_2mo.json"
    payload = json.loads(cal_path.read_text())
    assert len(payload.get("months") or []) == 2
    assert payload.get("money_day_ids")
    for e in payload.get("events") or []:
        assert e.get("promotion_allowed") is False
        assert e.get("date")


def test_packs_borough_cluster_and_no_invented_coords():
    events = [
        {
            "id": "a",
            "title": "Parade",
            "date": "2026-07-14",
            "borough": "Manhattan",
            "coordinate_status": "map_ready",
            "assignment_score": 400,
            "latitude": 40.7,
            "longitude": -74.0,
            "why_selected": ["keyword_civic_gathering"],
            "source": {"dataset": "tvpp-9vvx"},
            "lane": "approved_major",
        },
        {
            "id": "b",
            "title": "Market",
            "date": "2026-07-14",
            "borough": "Brooklyn",
            "coordinate_status": "list_only",
            "assignment_score": 300,
            "why_selected": ["keyword_market"],
            "source": {"dataset": "tvpp-9vvx"},
            "lane": "approved_major",
        },
    ]
    pack = packs.build_pack(events, day=date(2026, 7, 14), reference_today=date(2026, 7, 14), label="today")
    assert pack["total_events"] == 2
    assert pack["map_ready_count"] == 1
    assert any(c["borough"] == "Manhattan" for c in pack["borough_clusters"])
    assert pack["promotion_allowed"] is False


def test_admin_panel_wired():
    admin = (ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "index.html").read_text()
    assert "photographer-calendar-panel-v01.js" in admin
    assert "photographer-calendar-section" in admin
    panel = (ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "photographer-calendar-panel-v01.js").read_text()
    assert "TODAY" in panel
    assert "TOMORROW" in panel
    assert "assignment" in panel
    assert "->" not in panel


def test_assignment_mode_in_field_desk_app():
    app = (
        ROOT / "docs" / "field-desk-map-deploy" / "schema-v1-major-all-v01" / "app-schema-v1-major-all-v01.js"
    ).read_text()
    assert "assignmentMode" in app
    assert "loadMoneyDayCalendar" in app
    assert "assignmentMatches" in app


def test_window_bounds_two_months():
    today = date(2026, 7, 14)
    start, end, m1, m2 = cal.window_bounds(today)
    assert start == today
    assert m1 == date(2026, 7, 1)
    assert m2 == date(2026, 8, 1)
    assert end == date(2026, 8, 31)
