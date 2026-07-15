"""Tests for photographer assignment calendar (2-month premium/operator)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_photographer_assignment_calendar as cal  # noqa: E402


def test_score_flags_parade_and_excludes_routine_class():
    parade = {"title": "Puerto Rican Day Parade", "category": "civic", "significance": "major", "nycif": {"is_major": True}}
    score, rules, excluded = cal.score_row(parade, lane="approved_major")
    assert not excluded
    assert score >= 160
    assert any("parade" in r or "major" in r for r in rules)

    yoga = {
        "title": "Chair Yoga Fitness Class",
        "category": "fitness",
        "location": "ZIP 11226",
        "nycif": {"coordinate_status": "list_only"},
    }
    score2, rules2, excluded2 = cal.score_row(yoga, lane="review_high_signal")
    assert excluded2
    assert "routine_activity_excluded" in rules2 or "list_only_thin_location_excluded" in rules2


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
    item = cal.normalize_assignment(row, lane="approved_major", score=200, rules=["significance_major"])
    assert item["date"] == "2026-08-01"
    assert item["start_date_time"] == "2026-08-01T00:00:00.000"
    assert item["promotion_allowed"] is False


def test_committed_calendar_report_when_present():
    path = ROOT / "data" / "photographer_assignment_calendar_report.json"
    if not path.exists():
        pytest.skip("calendar not generated yet")
    report = json.loads(path.read_text())
    assert report.get("qa_pass") is True
    assert report.get("total_events", 0) > 0
    assert report.get("protected_files_untouched") is True
    cal_path = ROOT / "data" / "photographer_assignment_calendar_2mo.json"
    payload = json.loads(cal_path.read_text())
    assert len(payload.get("months") or []) == 2
    assert payload.get("premium_label")
    for e in payload.get("events") or []:
        assert e.get("promotion_allowed") is False
        assert e.get("date")


def test_admin_panel_wired():
    admin = (ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "index.html").read_text()
    assert "photographer-calendar-panel-v01.js" in admin
    assert "photographer-calendar-section" in admin
    panel = ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "photographer-calendar-panel-v01.js"
    assert panel.exists()
    assert "->" not in panel.read_text()


def test_window_bounds_two_months():
    today = date(2026, 7, 14)
    start, end, m1, m2 = cal.window_bounds(today)
    assert start == today
    assert m1 == date(2026, 7, 1)
    assert m2 == date(2026, 8, 1)
    assert end == date(2026, 8, 31)
