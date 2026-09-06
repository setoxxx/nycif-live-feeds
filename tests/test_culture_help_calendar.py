"""Fixture tests for rolling public-help Culture calendar fetchers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.culture import calendar_normalize as cal  # noqa: E402
from scripts.culture import common as culture_common  # noqa: E402
from scripts.culture import pull_aspca_mobile  # noqa: E402
from scripts.culture import pull_cuny_career_events  # noqa: E402
from scripts.culture import pull_dol_career_events  # noqa: E402
from scripts.culture import pull_nybc_blood_drives  # noqa: E402
from scripts.culture import pull_show_mobile_clinics  # noqa: E402
from scripts.culture import pull_workforce1_events  # noqa: E402
from scripts.culture import validate_before_publish as validator  # noqa: E402
from scripts.culture.common import default_reader_gates  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "culture"
SQL = ROOT / "supabase" / "migrations" / "20260906063000_culture_help_calendar_v1.sql"
PLAN = ROOT / "docs" / "CULTURE_COMMUNITY_ENGINEERING_PLAN.md"
REGISTRY = ROOT / "data" / "culture" / "cuny_career_source_registry.json"


def _patch_io(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    reports = tmp_path / "reports"
    monkeypatch.setattr(culture_common, "STAGING_DIR", staging)
    monkeypatch.setattr(culture_common, "REPORT_DIR", reports)
    for module in (
        pull_workforce1_events,
        pull_nybc_blood_drives,
        pull_show_mobile_clinics,
        pull_dol_career_events,
        pull_cuny_career_events,
        pull_aspca_mobile,
        validator,
    ):
        monkeypatch.setattr(module, "write_staging", culture_common.write_staging, raising=False)
        monkeypatch.setattr(module, "STAGING_DIR", staging, raising=False)
        monkeypatch.setattr(module, "REPORT_DIR", reports, raising=False)
    return staging, reports


def test_help_gates_stay_false():
    gates = default_reader_gates()
    assert gates["help_calendar_publication_enabled"] is False
    assert gates["blood_layer_enabled"] is False
    assert gates["jobs_layer_enabled"] is False
    assert gates["college_layer_enabled"] is False
    assert "blood_drive" in culture_common.CALENDAR_KINDS
    assert "pet_mobile" in cal.OCCURRENCE_KINDS


def test_normalize_drops_missing_title_or_start():
    assert cal.normalize_calendar_occurrence(
        occurrence_kind="job_fair",
        title="",
        source_name="t",
        source_dataset="t",
        start_at="2026-09-10",
    ) is None
    assert cal.normalize_calendar_occurrence(
        occurrence_kind="job_fair",
        title="Fair",
        source_name="t",
        source_dataset="t",
        start_at="",
    ) is None


def test_workforce1_fixture_and_refuses_invent(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    assert pull_workforce1_events.main([]) == 2
    assert (
        pull_workforce1_events.main(
            ["--fixture", str(FIXTURES / "workforce1_events.fixture.json")]
        )
        == 0
    )
    payload = culture_common.load_json(staging / "workforce1_events.json", {})
    assert payload["row_count"] == 2
    assert payload["promotion_allowed"] is False
    kinds = {row["occurrence_kind"] for row in payload["rows"]}
    assert kinds == {"job_fair", "workshop"}
    assert all(row["map_ready"] is False for row in payload["rows"])
    assert all(row["emoji"] == "💼" for row in payload["rows"])
    recruitment = next(row for row in payload["rows"] if row["occurrence_kind"] == "job_fair")
    assert recruitment["time_precision"] == "check_in_window"
    workshop = next(row for row in payload["rows"] if row["occurrence_kind"] == "workshop")
    assert workshop["start_at"].startswith("2026-09-11T00:00:00")


def test_nybc_and_show_fixtures(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    assert pull_nybc_blood_drives.main([]) == 2
    assert pull_nybc_blood_drives.main(["--live"]) == 3
    assert pull_nybc_blood_drives.main(["--fixture", str(FIXTURES / "nybc_blood_drives.fixture.json")]) == 0
    nybc = culture_common.load_json(staging / "nybc_blood_drives.json", {})
    assert nybc["row_count"] == 1
    assert nybc["rows"][0]["occurrence_kind"] == "blood_drive"
    assert nybc["rows"][0]["emoji"] == "🩸"
    assert nybc["rows"][0]["map_ready"] is False
    assert nybc["live_scrape_wired"] is False

    assert pull_show_mobile_clinics.main(["--fixture", str(FIXTURES / "show_mobile_clinics.fixture.json")]) == 0
    show = culture_common.load_json(staging / "show_mobile_clinics.json", {})
    assert show["row_count"] == 2
    kinds = {row["occurrence_kind"] for row in show["rows"]}
    assert kinds == {"mobile_clinic", "resource_van"}
    assert all(row["emoji"] == "🏥" for row in show["rows"])


def test_dol_filters_non_nyc(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    assert pull_dol_career_events.main(["--fixture", str(FIXTURES / "dol_career_events.fixture.json")]) == 0
    payload = culture_common.load_json(staging / "dol_career_events.json", {})
    assert payload["row_count"] == 1
    assert payload["rows"][0]["borough"] == "Brooklyn"
    assert "Albany" not in payload["rows"][0]["title"]
    assert payload["dropped_non_nyc_or_incomplete"] == 1


def test_cuny_registry_without_events_is_zero(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    assert pull_cuny_career_events.main(["--registry", str(REGISTRY)]) == 0
    empty = culture_common.load_json(staging / "cuny_career_events.json", {})
    assert empty["row_count"] == 0
    assert empty["source_count"] >= 6
    assert pull_cuny_career_events.main(
        [
            "--registry",
            str(REGISTRY),
            "--events-fixture",
            str(FIXTURES / "cuny_career_events.fixture.json"),
        ]
    ) == 0
    filled = culture_common.load_json(staging / "cuny_career_events.json", {})
    assert filled["row_count"] == 1
    assert filled["rows"][0]["emoji"] == "🎓"
    assert filled["rows"][0]["chip_id"] == "college"


def test_aspca_waitlist_zip_only(tmp_path, monkeypatch):
    staging, _reports = _patch_io(monkeypatch, tmp_path)
    assert pull_aspca_mobile.main(["--fixture", str(FIXTURES / "aspca_mobile.fixture.json")]) == 0
    payload = culture_common.load_json(staging / "aspca_mobile.json", {})
    row = payload["rows"][0]
    assert row["occurrence_kind"] == "pet_mobile"
    assert row["waitlist_gated"] is True
    assert row["pin_policy"] == "zip_area_only"
    assert row["lat"] is None
    assert row["map_ready"] is False


def test_validate_help_calendar_stays_unpublished(tmp_path, monkeypatch):
    _staging, reports = _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(validator, "HOWARD_CSV", tmp_path / "missing.csv")
    pull_workforce1_events.main(["--fixture", str(FIXTURES / "workforce1_events.fixture.json")])
    report = validator.validate()
    assert report["qa_pass"] is True
    assert report["publication_allowed"] is False
    assert report["calendar_row_counts"]["workforce1"] == 2
    assert report["invented_events"] is False
    assert (reports / "validate_before_publish.json").exists()


def test_sql_and_plan_document_help_kinds():
    sql = SQL.read_text(encoding="utf-8")
    for kind in ("blood_drive", "mobile_clinic", "job_fair", "workshop", "pet_mobile", "resource_van"):
        assert kind in sql
    assert "help_calendar_publication_enabled boolean not null default false" in sql
    plan = PLAN.read_text(encoding="utf-8")
    assert "🩸" in plan
    assert "kf2b-aeh5" in plan
    assert "donate.nybc.org" in plan
    assert "S.H.O.W." in plan or "SHOW" in plan
    assert "6:00 AM America/New_York" in plan
    assert "culture-help-calendar-daily.yml" in plan
    assert REGISTRY.exists()
    registry = culture_common.load_json(REGISTRY, {})
    assert registry.get("live_fetch_wired") is False
    assert registry.get("publication_allowed") is False
