#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ProjectedFeastDiscoveryTests(unittest.TestCase):
    def test_projected_feast_intake_artifact_exists(self) -> None:
        path = ROOT / "data/staging/projected_feast_events_map_intake.json"
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events") if isinstance(payload, dict) else []
        self.assertGreaterEqual(len(events), 100)

    def test_projected_feast_bulk_coverage_in_approved(self) -> None:
        approved = json.loads((ROOT / "data/events_discovery_v02_approved.json").read_text(encoding="utf-8"))
        projected = [
            e
            for e in approved.get("events", [])
            if e.get("nycif", {}).get("projected_feast_reference")
        ]
        self.assertGreaterEqual(len(projected), 100)

    def test_san_gennaro_in_approved_discovery(self) -> None:
        approved = json.loads((ROOT / "data/events_discovery_v02_approved.json").read_text(encoding="utf-8"))
        hits = [
            e
            for e in approved.get("events", [])
            if (e.get("source") or {}).get("source_event_id") == "feast-of-san-gennaro"
        ]
        self.assertEqual(len(hits), 1)
        event = hits[0]
        self.assertEqual(event["title"], "Feast of San Gennaro")
        self.assertEqual(str(event.get("end_date_time") or "")[:10], "2026-09-20")
        self.assertEqual(event["nycif"]["coordinate_status"], "map_ready")
        self.assertTrue(event["nycif"]["is_major"])


if __name__ == "__main__":
    unittest.main()
