"""Tests for News Desk assignment checklist builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_news_desk_assignment_checklist as build  # noqa: E402
import news_desk_checklist_common as nd  # noqa: E402


def test_clean_headline_fixes_c0_naming():
    assert "Co-Naming" in nd.clean_headline("Ol Dirty Bastard Street C0-Naming ceremony")


def test_field_desk_link_includes_date_and_borough():
    link = nd.field_desk_link("2026-07-25", "Brooklyn")
    assert "date=2026-07-25" in link
    assert "borough=Brooklyn" in link
    assert "assignment=1" in link


def test_odb_row_from_census_entry():
    entry = {
        "name": "Ol' Dirty Bastard Street Co-Naming Ceremony",
        "date": "2026-07-25",
        "start_time": "12:00",
        "end_time": "14:00",
        "borough": "Brooklyn",
        "route": "Claver Place",
        "event_kind": "street_co_naming",
        "permit_event_id": "945819",
        "confidence": "permit_confirmed",
        "editorial_priority": "highest",
        "source_layer": "editorial_anchor",
        "anchor_key": "odb-street-co-naming",
    }
    row = nd.row_from_census_entry(entry)
    assert row is not None
    assert row["story_lane"] == "street_co_naming"
    assert row["editorial_priority"] == "highest"
    assert row["checklist_id"] == "tvpp-9vvx:945819@2026-07-25"
    assert row["map_eligible"] is False


def test_merge_rows_keeps_higher_priority_and_score():
    a = nd.base_row(
        headline="A",
        day="2026-07-25",
        borough="Brooklyn",
        lane="parade_march",
        priority="high",
        assignment_score=300,
        source_layer="a",
    )
    b = nd.base_row(
        headline="A",
        day="2026-07-25",
        borough="Brooklyn",
        lane="parade_march",
        priority="highest",
        assignment_score=400,
        why_story=["photographer_money_day"],
        source_layer="b",
    )
    merged = nd.merge_rows(a, b)
    assert merged["editorial_priority"] == "highest"
    assert merged["assignment_score"] == 400
    assert "photographer_money_day" in merged["why_story"]


def test_production_build_passes_qa():
    checklist, report = build.build_checklist()
    assert report["qa_pass"] is True
    assert report["odb_present"] is True
    assert report["map_eligible_count"] == 0
    assert report["duplicate_checklist_ids"] == 0
    assert checklist["promotion_allowed"] is False

    odb = next(
        r
        for r in checklist["all_rows"]
        if r.get("permit_event_id") == "945819" or r.get("anchor_key") == "odb-street-co-naming"
    )
    assert odb["editorial_priority"] == "highest"
    assert odb["story_lane"] == "street_co_naming"
    assert "Co-Naming" in odb["story_headline"]
    assert odb["coordinate_status"] == "map_ready"
    assert odb["latitude"] is not None

    assert any(r["checklist_id"] == odb["checklist_id"] for r in checklist["priority_unchecked"])
    assert "by_story_lane" in checklist
    assert "street_co_naming" in checklist["by_story_lane"]
