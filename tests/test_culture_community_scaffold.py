"""Fail-closed tests for the Culture community scaffold."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.culture.common import (  # noqa: E402
    HOWARD_CSV,
    PLACE_KINDS,
    default_reader_gates,
    missing_howard_csv_message,
    safety_envelope,
)
from scripts.culture.import_curated_storefronts import main as import_main  # noqa: E402
from scripts.culture.pull_fdny_firehouses import main as pull_fdny  # noqa: E402
from scripts.culture.pull_nypd_precincts import main as pull_nypd  # noqa: E402
from scripts.culture.pull_shelters import main as pull_shelters  # noqa: E402
from scripts.culture import validate_before_publish as validator  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "culture"
SQL = ROOT / "supabase" / "migrations" / "20260906050000_culture_community_scaffold_v1.sql"
PLAN = ROOT / "docs" / "CULTURE_COMMUNITY_ENGINEERING_PLAN.md"


def test_safety_envelope_and_gates_fail_closed():
    envelope = safety_envelope()
    assert envelope["promotion_allowed"] is False
    assert envelope["business_publication_enabled"] is False
    assert envelope["wordpress_modified"] is False
    assert envelope["location_cache_modified"] is False
    gates = default_reader_gates()
    assert all(value is False for value in gates.values())
    assert "storefront" in PLACE_KINDS
    assert "civic_nypd" in PLACE_KINDS


def test_howard_csv_is_not_invented():
    assert not HOWARD_CSV.exists()
    message = missing_howard_csv_message(HOWARD_CSV)
    assert "will not invent" in message
    assert import_main(["--csv", str(HOWARD_CSV)]) == 2


def test_import_requires_real_rows(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("business_name,address\n", encoding="utf-8")
    assert import_main(["--csv", str(empty)]) == 2


def test_import_stages_pending_only(tmp_path, monkeypatch):
    csv_path = tmp_path / "howard.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["business_name", "address", "borough", "lat", "lng", "place_kind"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "business_name": "Howard Listed Bakery",
                "address": "1 Test Street",
                "borough": "Brooklyn",
                "lat": "40.65",
                "lng": "-73.95",
                "place_kind": "storefront",
            }
        )
    staging = tmp_path / "staging"
    reports = tmp_path / "reports"
    monkeypatch.setattr(validator, "STAGING_DIR", staging)
    from scripts.culture import import_curated_storefronts as importer
    from scripts.culture import common as culture_common

    monkeypatch.setattr(culture_common, "STAGING_DIR", staging)
    monkeypatch.setattr(culture_common, "REPORT_DIR", reports)
    monkeypatch.setattr(importer, "write_staging", culture_common.write_staging)

    assert importer.main(["--csv", str(csv_path)]) == 0
    payload = culture_common.load_json(staging / "curated_storefronts.json", {})
    assert payload["row_count"] == 1
    row = payload["rows"][0]
    assert row["review_status"] == "pending"
    assert row["promotion_allowed"] is False
    assert row["map_eligible"] is False
    assert row["qualification_hint"] == "Howard Listed Bakery"
    assert row["is_sample"] is False


def test_pulls_stage_civic_without_publication(tmp_path, monkeypatch):
    from scripts.culture import common as culture_common
    from scripts.culture import pull_fdny_firehouses as fdny_mod
    from scripts.culture import pull_nypd_precincts as nypd_mod
    from scripts.culture import pull_shelters as shelter_mod

    staging = tmp_path / "staging"
    reports = tmp_path / "reports"
    for module in (culture_common, nypd_mod, fdny_mod, shelter_mod):
        monkeypatch.setattr(module, "STAGING_DIR", staging, raising=False)
        monkeypatch.setattr(module, "REPORT_DIR", reports, raising=False)
    monkeypatch.setattr(nypd_mod, "write_staging", culture_common.write_staging)
    monkeypatch.setattr(fdny_mod, "write_staging", culture_common.write_staging)
    monkeypatch.setattr(shelter_mod, "write_staging", culture_common.write_staging)

    assert pull_nypd(["--fixture", str(FIXTURES / "nypd_precincts.fixture.json")]) == 0
    assert pull_fdny(["--fixture", str(FIXTURES / "fdny_firehouses.fixture.json")]) == 0
    assert pull_shelters(["--fixture", str(FIXTURES / "shelters_census_only.fixture.json")]) == 0

    nypd = culture_common.load_json(staging / "nypd_precincts.json", {})
    fdny = culture_common.load_json(staging / "fdny_firehouses.json", {})
    shelters = culture_common.load_json(staging / "shelters.json", {})

    assert nypd["promotion_allowed"] is False
    assert nypd["rows"][0]["lat"] is None
    assert nypd["rows"][0]["emoji"] == "👮"
    assert fdny["rows"][0]["emoji"] == "🚒"
    assert fdny["rows"][0]["promotion_allowed"] is False
    assert shelters["census_only"] is True
    assert shelters["rows"][0]["lat"] is None
    assert shelters["rows"][0]["addressable"] is False


def test_validate_blocks_publication_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(validator, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(validator, "HOWARD_CSV", tmp_path / "missing.csv")
    report = validator.validate()
    assert report["qa_pass"] is True
    assert report["publication_allowed"] is False
    assert report["would_publish"] is False
    assert report["accepted_count"] == 0
    assert report["invented_storefronts"] is False
    assert report["howard_csv_present"] is False


def test_validate_fails_if_gate_flipped(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(validator, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(validator, "HOWARD_CSV", tmp_path / "missing.csv")
    report = validator.validate({"business_publication_enabled": True})
    assert report["qa_pass"] is False
    assert report["publication_allowed"] is False


def test_sql_draft_keeps_gates_false():
    text = SQL.read_text(encoding="utf-8")
    assert "business_publication_enabled boolean not null default false" in text
    assert "place_kind" in text
    assert "culture_civic_facility_v1" in text
    assert "culture_calendar_occurrence_v1" in text
    assert "culture_resource_v1" in text
    assert "enable row level security" in text
    assert "Do not flip" in text or "stays false" in text.lower() or "default false" in text
    # Force-false apply block
    assert "business_publication_enabled = false" in text
    assert "civic_nypd" in text


def test_plan_and_cross_repo_notes_exist():
    text = PLAN.read_text(encoding="utf-8")
    assert "Howard must drop the ~91 CSV" in text
    assert "business_publication_enabled" in text
    assert "y76i-bdw7" in text
    assert "hc8x-tcnd" in text
    assert "g9nt-57fp" in text
    assert "WordPress" in text
    assert "service_role" in text
    pipeline = ROOT / "docs/cross-repo/CULTURE_COMMUNITY_NYCIF_DATA_PIPELINE.md"
    ios = ROOT / "docs/cross-repo/CULTURE_COMMUNITY_NYCINFOCUS.md"
    assert pipeline.exists()
    assert ios.exists()
    assert "REVIEW_NAME_LEAD_NEEDS_EVIDENCE" in pipeline.read_text(encoding="utf-8")
    assert "service_role" in ios.read_text(encoding="utf-8")


def test_pull_refuses_without_source():
    assert pull_nypd([]) == 2
    assert pull_fdny([]) == 2
    assert pull_shelters([]) == 2


def test_cli_validate_exit_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(validator, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(validator, "HOWARD_CSV", tmp_path / "missing.csv")
    assert validator.main([]) == 0


def test_scripts_compile():
    script_dir = ROOT / "scripts" / "culture"
    result = subprocess.run(
        [sys.executable, "-m", "compileall", str(script_dir), str(Path(__file__))],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
