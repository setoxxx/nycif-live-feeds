#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.apply_supplemental_overlap_key_coord_conflict_audit import (  # noqa: E402
    apply_finding,
    location_aware_overlap_key,
    match_row,
    verify_export_counts,
)


class ApplyOverlapKeyConflictAuditTests(unittest.TestCase):
    def test_location_aware_overlap_key_uses_borough_and_place(self) -> None:
        row = {
            "borough": "SI",
            "display_location": "Midland Beach Splash Plaza (in Franklin D. Roosevelt Boardwalk and Beach)",
            "source_event_id": "2169466",
        }
        key = location_aware_overlap_key("zumba|2026-07-25", row)
        self.assertEqual(key, "zumba|2026-07-25|SI|midland beach splash plaza")

    def test_match_row_by_source_event_id(self) -> None:
        row = {
            "overlap_key": "bootcamp|2026-07-16",
            "source_event_id": "1055516",
            "proposed_lat": 40.75,
            "proposed_lng": -73.98,
        }
        snapshot = {"source_event_id": "1055516", "lat": 40.75, "lng": -73.98}
        self.assertTrue(match_row(row, snapshot, "bootcamp|2026-07-16"))

    def test_apply_dedupe_rejects_alternate_row(self) -> None:
        queue = [
            {
                "overlap_key": "test|2026-07-01",
                "source_event_id": "keep",
                "proposed_lat": 40.75,
                "proposed_lng": -73.98,
                "manual_review_status": "approved",
            },
            {
                "overlap_key": "test|2026-07-01",
                "source_event_id": "drop",
                "proposed_lat": 40.76,
                "proposed_lng": -73.99,
                "manual_review_status": "approved",
            },
        ]
        finding = {
            "overlap_key": "test|2026-07-01",
            "recommendation": "merge_dedupe_keep_better_geocode",
            "reason": "same venue",
            "alternate_row": {
                "source_event_id": "drop",
                "lat": 40.76,
                "lng": -73.99,
            },
        }
        applied: list[dict] = []
        unmatched: list[dict] = []
        updated = apply_finding(
            queue,
            finding,
            reviewed_at_utc="2026-07-18T00:00:00+00:00",
            applied=applied,
            unmatched=unmatched,
        )
        statuses = {row["source_event_id"]: row["manual_review_status"] for row in updated}
        self.assertEqual(statuses["keep"], "approved")
        self.assertEqual(statuses["drop"], "rejected")
        self.assertEqual(len(applied), 1)

    def test_apply_split_rekeys_both_rows(self) -> None:
        queue = [
            {
                "overlap_key": "zumba|2026-07-25",
                "source_event_id": "1115256",
                "borough": "Qn",
                "display_location": "Gymnasium (Court) in Al Oerter Recreation Center",
                "proposed_lat": 40.751392,
                "proposed_lng": -73.834009,
                "manual_review_status": "approved",
            },
            {
                "overlap_key": "zumba|2026-07-25",
                "source_event_id": "2169466",
                "borough": "SI",
                "display_location": "Midland Beach Splash Plaza (in Franklin D. Roosevelt Boardwalk and Beach)",
                "proposed_lat": 40.57849884033203,
                "proposed_lng": -74.07759857177734,
                "manual_review_status": "approved",
            },
        ]
        finding = {
            "overlap_key": "zumba|2026-07-25",
            "recommendation": "split_overlap_key_keep_both_pins",
            "row_a": {
                "source_event_id": "1115256",
                "lat": 40.751392,
                "lng": -73.834009,
            },
            "row_b": {
                "source_event_id": "2169466",
                "lat": 40.57849884033203,
                "lng": -74.07759857177734,
            },
        }
        applied: list[dict] = []
        unmatched: list[dict] = []
        updated = apply_finding(
            queue,
            finding,
            reviewed_at_utc="2026-07-18T00:00:00+00:00",
            applied=applied,
            unmatched=unmatched,
        )
        keys = {row["source_event_id"]: row["overlap_key"] for row in updated}
        self.assertEqual(keys["1115256"], "zumba|2026-07-25|Qn|gymnasium")
        self.assertEqual(keys["2169466"], "zumba|2026-07-25|SI|midland beach splash plaza")
        self.assertEqual(len(applied), 2)

    def test_verify_export_counts_targets(self) -> None:
        export_path = ROOT / "data/supplemental_approved_export_feed.json"
        if not export_path.exists():
            self.skipTest("export feed snapshot missing")
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        counts = verify_export_counts(payload["events"])
        self.assertEqual(counts["export_event_count"], len(payload["events"]))
        self.assertEqual(counts["remaining_coord_conflict_pair_count"], 0)
        self.assertTrue(counts["remaining_coord_conflict_pair_count_match"])


if __name__ == "__main__":
    unittest.main()
