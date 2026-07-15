"""Tests for viral recurrence memory (last-year ↔ money-day matches)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_photographer_viral_recurrence as viral  # noqa: E402
import sync_nyc_permits_historical as hist  # noqa: E402


def test_schema_parity_documents_no_applicant():
    parity = hist.schema_parity_ok()
    assert parity["parity_confirmed"] is True
    assert parity["applicant_org_in_open_data"] is False
    assert "event_id" in parity["shared_public_columns"]


def test_name_and_place_scoring_returning_likely():
    current = {
        "id": "tvpp-9vvx:1@2026-07-15",
        "title": "Elmhurst Greenmarket Tuesday",
        "date": "2026-07-15",
        "borough": "Queens",
        "display_location": "41 AVENUE between 80 STREET and 81 STREET",
        "category": "market",
        "source": {"dataset": "tvpp-9vvx", "source_event_id": "1"},
        "coordinate_status": "map_ready",
    }
    hist_row = {
        "event_id": "999",
        "cemsid": "1,",
        "event_name": "Elmhurst Greenmarket Tuesday",
        "start_date_time": "2025-07-16T08:00:00.000",
        "event_borough": "Queens",
        "event_location": "41 AVENUE between 80 STREET and 81 STREET",
        "event_type": "Farmers Market",
        "street_closure_type": "Sidewalk",
        "police_precinct": "110,",
    }
    score, reasons, label = viral.score_match(current, hist_row)
    assert score >= 85
    assert label == "returning_likely"
    assert any("name_" in r or "place_" in r for r in reasons)


def test_season_too_far_zeroes_match():
    current = {
        "title": "Pride Parade",
        "date": "2026-06-28",
        "borough": "Manhattan",
        "display_location": "Fifth Avenue",
        "source": {"source_event_id": "2"},
    }
    hist_row = {
        "event_name": "Pride Parade",
        "start_date_time": "2025-12-01T12:00:00.000",
        "event_borough": "Manhattan",
        "event_location": "Fifth Avenue",
    }
    score, reasons, _label = viral.score_match(current, hist_row)
    assert score == 0
    assert any("season_too_far" in r for r in reasons)


def test_foil_left_join_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(viral, "DATA_DIR", tmp_path)
    (tmp_path / "sapo_foil_operator_index.json").write_text(
        json.dumps(
            {
                "schema_version": "sapo-foil-operator-index-v1",
                "operators": [
                    {
                        "event_id": "999",
                        "applicant_org": "Example Markets LLC",
                        "source": "foil",
                        "notes": "test",
                    }
                ],
            }
        )
    )
    idx = viral.load_foil_index()
    joined = viral.foil_for("999", None, idx)
    assert joined["applicant_org"] == "Example Markets LLC"


def test_committed_artifacts_when_present():
    report_path = ROOT / "data" / "photographer_viral_recurrence_report.json"
    if not report_path.exists():
        pytest.skip("viral recurrence not built yet")
    report = json.loads(report_path.read_text())
    assert report.get("qa_pass") is True
    assert report.get("match_count", 0) > 0
    assert (report.get("label_counts") or {}).get("returning_likely", 0) > 0
    hist_snap = json.loads((ROOT / "data" / "nyc_permits_historical_snapshot.json").read_text())
    assert hist_snap.get("dataset") == "bkfu-528j"
    assert hist_snap.get("row_count", 0) > 0
    assert hist_snap.get("schema_parity", {}).get("applicant_org_in_open_data") is False
    foil = json.loads((ROOT / "data" / "sapo_foil_operator_index.json").read_text())
    assert foil.get("operators") == []
    pack = json.loads((ROOT / "data" / "photographer_viral_recurrence_pack_next_14d.json").read_text())
    assert pack.get("crowd_magnet_count", 0) > 0
    for m in pack.get("crowd_magnets") or []:
        assert m.get("coordinate_status") == "map_ready"
        assert m.get("certified_pin") is True
        assert m.get("latitude") is not None and m.get("longitude") is not None


def test_admin_panel_has_returning_section():
    panel = (
        ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "photographer-calendar-panel-v01.js"
    ).read_text()
    assert "Returning from last year" in panel
    assert "photographer_viral_recurrence_pack_next_14d.json" in panel
    assert "->" not in panel


def test_daily_sync_allowlists_viral_scripts():
    text = (ROOT / "scripts" / "run_daily_people_facing_desk_sync.py").read_text()
    assert "sync_nyc_permits_historical.py" in text
    assert "build_photographer_viral_recurrence.py" in text
    assert "build_pin_integrity_gate.py" in text
    assert "build_photographer_shoot_day_certified.py" in text
    assert "pin_report.get(\"qa_pass\"" in text or 'pin_report.get("qa_pass"' in text


def test_admin_panel_has_pin_integrity_and_shoot_day():
    panel = (
        ROOT / "docs" / "field-desk-admin-deploy" / "admin" / "photographer-calendar-panel-v01.js"
    ).read_text()
    assert "Pin Integrity" in panel
    assert "SHOOT DAY CERTIFIED" in panel
    assert "pin_integrity_gate_report.json" in panel
    assert "photographer_shoot_day_certified_pack.json" in panel
    assert "->" not in panel


def test_field_desk_refuses_oob_pins():
    app = (
        ROOT / "docs" / "field-desk-map-deploy" / "schema-v1-major-all-v01" / "app-schema-v1-major-all-v01.js"
    ).read_text()
    assert "nycCertifiedPin" in app
    assert "NYC_BOX" in app
    assert "swap_suspected" in app
    assert "LIST ONLY never get fake markers" in app

