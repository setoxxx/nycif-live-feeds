"""Tests for citywide parade / procession census builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_citywide_parade_census as build  # noqa: E402
import citywide_parade_census_common as census  # noqa: E402


FIXTURE_PERMIT_ROWS = [
    {
        "source_event_id": "903587",
        "source_dataset": "tvpp-9vvx",
        "event_name": "Gratitude 5k",
        "event_type": "Special Event",
        "event_borough": "Queens",
        "event_location": "Forest Park: Forest Park Drive (Race)",
        "start_date_time": "2026-11-26T08:00:00.000",
        "end_date_time": "2026-11-26T10:00:00.000",
        "event_agency": "Parks Department",
        "street_closure_type": "N/A",
    },
    {
        "source_event_id": "934705",
        "source_dataset": "tvpp-9vvx",
        "event_name": "Colombian Day Parade",
        "event_type": "Parade",
        "event_borough": "Queens",
        "event_location": "Northern Boulevard",
        "start_date_time": "2026-07-26T12:00:00.000",
        "end_date_time": "2026-07-26T15:00:00.000",
        "event_agency": "Police Department",
        "street_closure_type": "Full Street Closure",
    },
    {
        "source_event_id": "999001",
        "source_dataset": "tvpp-9vvx",
        "event_name": "QBAC Marching Band Rehearsal",
        "event_type": "Special Event",
        "event_borough": "Manhattan",
        "event_location": "Parade Ground: Field 1",
        "start_date_time": "2026-07-16T10:00:00.000",
        "end_date_time": "2026-07-16T12:00:00.000",
        "event_agency": "Parks Department",
        "street_closure_type": "N/A",
    },
    {
        "source_event_id": "999002",
        "source_dataset": "tvpp-9vvx",
        "event_name": "Routine Yoga in the Park",
        "event_type": "Special Event",
        "event_borough": "Brooklyn",
        "event_location": "Prospect Park",
        "start_date_time": "2026-08-01T09:00:00.000",
        "end_date_time": "2026-08-01T10:00:00.000",
        "event_agency": "Parks Department",
        "street_closure_type": "N/A",
    },
]


def test_parade_ground_and_rehearsal_excluded():
    ok, reason = census.is_census_candidate(FIXTURE_PERMIT_ROWS[2])
    assert not ok
    assert reason == "parade_ground_excluded"


def test_routine_fitness_not_in_census():
    ok, _ = census.is_census_candidate(FIXTURE_PERMIT_ROWS[3])
    assert not ok


def test_gratitude_5k_included_on_thanksgiving_morning():
    ok, reason = census.is_census_candidate(FIXTURE_PERMIT_ROWS[0])
    assert ok
    assert reason in {"census_keyword_match", "typed_street_event_with_census_keyword"}


def test_colombian_parade_matches_anchor_with_near_date(tmp_path):
    registry_path = ROOT / "data" / "nycif_citywide_parade_anchor_registry.json"
    permit_path = tmp_path / "permits.json"
    permit_path.write_text(json.dumps(FIXTURE_PERMIT_ROWS), encoding="utf-8")

    snapshot, report = build.build_census(
        anchor_registry_path=registry_path,
        permit_snapshot_path=permit_path,
    )

    colombian = next(
        e for e in snapshot["entries"] if e.get("anchor_key") == "colombian-cultural-parade-queens"
    )
    assert colombian["permit_status"] == "permit_matched"
    assert colombian["permit_event_id"] == "934705"
    assert colombian["confidence"] == "permit_confirmed"

    gratitude = next(e for e in snapshot["entries"] if e.get("name") == "Gratitude 5k")
    assert gratitude["source_layer"] == "permit_extract"
    assert gratitude["borough"] == "Queens"
    assert gratitude["map_eligible"] is False

    assert report["qa_pass"] is True
    assert all(not e.get("map_eligible") for e in snapshot["entries"])


def test_borough_queues_cover_required_buckets(tmp_path):
    registry_path = ROOT / "data" / "nycif_citywide_parade_anchor_registry.json"
    permit_path = tmp_path / "permits.json"
    permit_path.write_text(json.dumps(FIXTURE_PERMIT_ROWS), encoding="utf-8")
    snapshot, _ = build.build_census(
        anchor_registry_path=registry_path,
        permit_snapshot_path=permit_path,
    )
    queues = snapshot["borough_queues"]
    for bucket in (
        "Manhattan",
        "Brooklyn",
        "Queens",
        "Bronx",
        "Staten Island",
        "Multi-borough",
        "Metropolitan reference outside NYC",
    ):
        assert bucket in queues
    assert len(queues["Queens"]) >= 1
    assert len(queues["Multi-borough"]) >= 1


def test_production_build_passes_qa():
    snapshot, report = build.build_census()
    assert report["anchor_count"] >= 40
    assert report["permit_extracted_count"] > 0
    assert report["qa_pass"] is True
    assert report["map_eligible_count"] == 0
    assert snapshot["promotion_allowed"] is False
