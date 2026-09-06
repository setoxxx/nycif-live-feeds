"""Fail-closed tests for Culture calendar/civic staging → live-table load."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.culture import load_calendar_civic_staging as loader  # noqa: E402
from scripts.culture import pull_fdny_firehouses  # noqa: E402
from scripts.culture import pull_nypd_precincts  # noqa: E402
from scripts.culture import pull_shelters  # noqa: E402
from scripts.culture import pull_workforce1_events  # noqa: E402
from scripts.culture import common as culture_common  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "culture"
DAILY = ROOT / ".github" / "workflows" / "culture-help-calendar-daily.yml"
WEEKLY = ROOT / ".github" / "workflows" / "culture-civic-weekly.yml"
HOWARD = ROOT / "docs" / "CULTURE_CALENDAR_CIVIC_PUBLICATION.md"


def _patch_io(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    reports = tmp_path / "reports"
    monkeypatch.setattr(culture_common, "STAGING_DIR", staging)
    monkeypatch.setattr(culture_common, "REPORT_DIR", reports)
    monkeypatch.setattr(loader, "STAGING_DIR", staging)
    monkeypatch.setattr(loader, "REPORT_DIR", reports)
    for module in (pull_workforce1_events, pull_nypd_precincts, pull_fdny_firehouses, pull_shelters):
        monkeypatch.setattr(module, "write_staging", culture_common.write_staging, raising=False)
        monkeypatch.setattr(module, "STAGING_DIR", staging, raising=False)
        monkeypatch.setattr(module, "REPORT_DIR", reports, raising=False)
    return staging, reports


def test_calendar_row_forces_unpublished_and_keeps_clock():
    mapped = loader.calendar_row_from_staging(
        {
            "occurrence_id": "abc",
            "calendar_kind": "job_fair",
            "occurrence_kind": "job_fair",
            "title": "Workforce1 fair",
            "start_at": "2026-09-10T09:00:00",
            "lat": 40.65,
            "lng": -73.95,
            "map_ready": True,
            "promotion_allowed": True,
            "pin_policy": "certified_pin",
            "is_sample": True,
            "review_status": "pending",
        }
    )
    assert mapped is not None
    assert mapped["map_ready"] is False
    assert mapped["promotion_allowed"] is False
    assert mapped["is_sample"] is False
    assert mapped["pin_policy"] == "list_only"
    assert mapped["lat"] == 40.65
    assert mapped["start_at"].startswith("2026-09-10T09:00:00")
    assert mapped["review_status"] == "pending"


def test_calendar_row_drops_missing_title_or_start():
    assert loader.calendar_row_from_staging({"occurrence_id": "x", "title": "", "start_at": "2026-09-10", "calendar_kind": "job_fair"}) is None
    assert loader.calendar_row_from_staging({"occurrence_id": "x", "title": "Fair", "start_at": "", "calendar_kind": "job_fair"}) is None


def test_civic_census_row_never_gets_coords():
    mapped = loader.civic_row_from_staging(
        {
            "facility_id": "s1",
            "place_kind": "shelter",
            "source_dataset": "g9nt-57fp",
            "source_facility_id": "Brooklyn",
            "display_name": "Shelter census row (Brooklyn)",
            "census_only": True,
            "lat": 40.65,
            "lng": -73.95,
            "addressable": True,
            "map_eligible": True,
            "promotion_allowed": True,
        },
        default_kind="shelter",
    )
    assert mapped is not None
    assert mapped["lat"] is None
    assert mapped["lng"] is None
    assert mapped["addressable"] is False
    assert mapped["map_eligible"] is False
    assert mapped["promotion_allowed"] is False
    assert mapped["geometry"] is None


def test_preserve_accepted_existing_row():
    incoming = loader.calendar_row_from_staging(
        {
            "occurrence_id": "keep",
            "calendar_kind": "job_fair",
            "occurrence_kind": "job_fair",
            "title": "Updated title",
            "start_at": "2026-09-10T09:00:00-04:00",
        }
    )
    existing = {
        "occurrence_id": "keep",
        "review_status": "ACCEPTED",
        "manual_review_status": "approved",
        "manual_reviewer": "howard",
        "manual_reviewed_at_utc": "2026-09-06T12:00:00+00:00",
        "approval_decision_reason": "official SODA",
        "promotion_allowed": True,
        "map_ready": True,
    }
    merged = loader.merge_preserve_review(incoming, existing, id_field="occurrence_id")
    assert merged["title"] == "Updated title"
    assert merged["review_status"] == "ACCEPTED"
    assert merged["promotion_allowed"] is True
    assert merged["manual_reviewer"] == "howard"
    assert merged["map_ready"] is True


def test_loader_maps_fixture_pulls_without_writing(tmp_path, monkeypatch):
    staging, reports = _patch_io(monkeypatch, tmp_path)
    assert pull_workforce1_events.main(["--fixture", str(FIXTURES / "workforce1_events.fixture.json")]) == 0
    assert pull_nypd_precincts.main(["--fixture", str(FIXTURES / "nypd_precincts.fixture.json")]) == 0
    assert pull_fdny_firehouses.main(["--fixture", str(FIXTURES / "fdny_firehouses.fixture.json")]) == 0
    assert pull_shelters.main(["--fixture", str(FIXTURES / "shelters_census_only.fixture.json")]) == 0
    assert loader.main(["--dataset", "all", "--staging-dir", str(staging)]) == 0
    report = json.loads((reports / "calendar_civic_load_report.json").read_text(encoding="utf-8"))
    assert report["applied"] is False
    assert report["publication_allowed"] is False
    assert report["gates_touched"] is False
    assert report["calendar_row_count"] == 2
    assert report["civic_row_count"] == 3
    assert report["civic"]["shelter_census_only"] is True
    assert report["event_occurrences_modified"] is False
    payload = json.loads((reports / "calendar_civic_load_payload.json").read_text(encoding="utf-8"))
    assert all(row["promotion_allowed"] is False for row in payload["calendar_rows"])
    assert all(row["map_ready"] is False for row in payload["calendar_rows"])
    assert all(row["map_eligible"] is False for row in payload["civic_rows"])


def test_write_target_allowlist():
    try:
        loader.validate_write_target({"SUPABASE_URL": "https://evil.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "x"})
    except loader.LoadError as exc:
        assert "approved" in str(exc)
    else:
        raise AssertionError("expected LoadError")
    try:
        loader.validate_write_target({"SUPABASE_URL": loader.APPROVED_SUPABASE_URL})
    except loader.LoadError as exc:
        assert "SUPABASE_SERVICE_ROLE_KEY" in str(exc)
    else:
        raise AssertionError("expected LoadError")


def test_emit_sql_does_not_update_settings(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    pull_workforce1_events.main(["--fixture", str(FIXTURES / "workforce1_events.fixture.json")])
    sql_path = tmp_path / "load.sql"
    assert loader.main(["--dataset", "calendar", "--staging-dir", str(staging), "--emit-sql", str(sql_path)]) == 0
    sql = sql_path.read_text(encoding="utf-8")
    assert "UPDATE public.culture_reader_settings" not in sql
    assert "calendar_publication_enabled = true" not in sql
    assert "civic_publication_enabled = true" not in sql
    assert "INSERT INTO public.culture_calendar_occurrence_v1" in sql
    assert "refusing load: calendar_publication_enabled is true" in sql
    assert "event_occurrences" not in sql
    assert "culture_place_beta_v1" not in sql


def test_daily_workflow_loads_calendar_without_flipping_gates():
    text = DAILY.read_text(encoding="utf-8")
    assert "scripts/culture/load_calendar_civic_staging.py" in text
    assert "--dataset calendar" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "gates_touched" in text or "gates were not written" in text.lower() or "Gates were not written" in text
    for forbidden in (
        "calendar_publication_enabled: true",
        "civic_publication_enabled: true",
        "help_calendar_publication_enabled: true",
        "business_publication_enabled: true",
            "supabase functions deploy",
            "wordpress.com",
        ):
        assert forbidden.lower() not in text.lower(), forbidden


def test_weekly_workflow_loads_civic_without_flipping_gates():
    text = WEEKLY.read_text(encoding="utf-8")
    assert 'cron: "0 10 * * 1"' in text
    assert "scripts/culture/pull_nypd_precincts.py" in text
    assert "scripts/culture/pull_fdny_firehouses.py" in text
    assert "scripts/culture/pull_shelters.py" in text
    assert "scripts/culture/load_calendar_civic_staging.py" in text
    assert "--dataset civic" in text
    assert "calendar_publication_enabled: true" not in text
    assert "civic_publication_enabled: true" not in text


def test_howard_flip_doc_is_manual_only():
    text = HOWARD.read_text(encoding="utf-8")
    assert "calendar_publication_enabled" in text
    assert "civic_publication_enabled" in text
    assert "ACCEPTED" in text
    assert "promotion_allowed" in text
    assert "Do not run this during the gated backfill" in text or "after review" in text.lower()
