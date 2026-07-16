"""Tests for major radar rebuild script."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_major_radar_map_events as major  # noqa: E402


def test_preserves_hard_written_rows(tmp_path):
    existing = tmp_path / "major.json"
    existing.write_text(
        json.dumps(
            [
                {
                    "id": "nypd-hardwrite-test",
                    "title": "NYPD Field Intel: Test Fair",
                    "date": "2026-08-01",
                    "_hard_written": True,
                    "field_default": True,
                    "priority_score": 500,
                }
            ]
        ),
        encoding="utf-8",
    )
    census = tmp_path / "census.json"
    census.write_text(
        json.dumps(
            {
                "priority_events": [
                    {
                        "name": "Colombian Day Parade",
                        "date": "2026-07-26",
                        "borough": "Queens",
                        "permit_event_id": "934705",
                        "editorial_priority": "high",
                        "event_kind": "parade",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    photo = tmp_path / "photo.json"
    photo.write_text(json.dumps({"events": []}), encoding="utf-8")
    anchor = tmp_path / "anchors.json"
    anchor.write_text(json.dumps({"anchors": []}), encoding="utf-8")

    rows, report = major.build_major_radar(
        census_path=census,
        photo_path=photo,
        anchor_path=anchor,
        existing_path=existing,
    )
    hard = [r for r in rows if r.get("_hard_written")]
    assert len(hard) == 1
    assert hard[0]["id"] == "nypd-hardwrite-test"
    assert report["hard_written_preserved"] == 1
    assert any(r.get("source_event_id") == "934705" for r in rows)
