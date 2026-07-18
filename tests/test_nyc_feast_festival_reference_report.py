#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_nyc_feast_festival_reference_report import alias_hits, build, looks_like_feast_or_fair  # noqa: E402


class FeastReferenceReportTests(unittest.TestCase):
    def test_empty_title_does_not_match_alias(self) -> None:
        self.assertFalse(alias_hits("", ["St. Frances Cabrini Feast"]))

    def test_mount_carmel_seed_confirms_in_raw_snapshot(self) -> None:
        seed = json.loads((ROOT / "data/staging/nyc_feast_festival_reference_seed.json").read_text())["entries"]
        raw = json.loads((ROOT / "data/raw_nyc_open_data_snapshot.json").read_text())
        reference, report = build(seed, raw)
        mount = next(e for e in reference["entries"] if e["key"] == "our-lady-of-mount-carmel-brooklyn")
        self.assertEqual(mount["match_status"], "confirmed_permit_id")
        self.assertEqual(mount["raw_match"]["source_event_id"], "906428")
        self.assertGreaterEqual(report["confirmed_in_raw_snapshot"], 1)

    def test_sports_permit_is_not_treated_as_feast(self) -> None:
        row = {
            "event_name": None,
            "event_type": "Sport - Adult",
            "event_location": "Central Park: Great Lawn-Softball-01",
        }
        self.assertFalse(looks_like_feast_or_fair(row))


if __name__ == "__main__":
    unittest.main()
