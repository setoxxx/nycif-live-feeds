#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bulk_import_feast_festival_seed import merge_seed  # noqa: E402


def _entry(key: str, name: str, *, display: str = "Main St, Brooklyn") -> dict:
    return {
        "key": key,
        "canonical_name": name,
        "projected_start": "2026-08-01",
        "projected_end": "2026-08-02",
        "borough": "Brooklyn",
        "display_location": display,
        "event_kind": "street_fair",
    }


class BulkImportFeastFestivalSeedTests(unittest.TestCase):
    def test_append_only_does_not_overwrite_existing(self) -> None:
        seed = {
            "artifact_type": "nyc_feast_festival_reference_seed",
            "version": 1,
            "entries": [_entry("existing-feast", "Existing Feast", display="Keep This")],
        }
        patch = [
            _entry("existing-feast", "Overwritten Name", display="Should Not Apply"),
            _entry("new-feast", "New Feast"),
        ]
        merged, report = merge_seed(seed, patch, fill_missing_display=False)

        by_key = {e["key"]: e for e in merged["entries"]}
        self.assertEqual(by_key["existing-feast"]["display_location"], "Keep This")
        self.assertEqual(by_key["existing-feast"]["canonical_name"], "Existing Feast")
        self.assertIn("new-feast", by_key)
        self.assertEqual(report["added_count"], 1)
        self.assertEqual(report["skipped_duplicate_count"], 1)
        self.assertTrue(report["qa_pass"])

    def test_fill_missing_display_only_when_absent(self) -> None:
        seed = {
            "entries": [
                {
                    **_entry("no-display", "No Display"),
                    "display_location": "",
                }
            ]
        }
        patch = [_entry("no-display", "No Display", display="Filled In")]
        merged, report = merge_seed(seed, patch, fill_missing_display=True)

        by_key = {e["key"]: e for e in merged["entries"]}
        self.assertEqual(by_key["no-display"]["display_location"], "Filled In")
        self.assertEqual(report["filled_display_location_count"], 1)
        self.assertEqual(report["added_count"], 0)

    def test_committed_seed_has_bulk_merge_qa_pass(self) -> None:
        report_path = ROOT / "data/reports/nyc_feast_festival_seed_bulk_merge_report.json"
        self.assertTrue(report_path.exists(), "Run bulk_import_feast_festival_seed.py first")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["qa_pass"])
        self.assertGreaterEqual(report["seed_after"], 160)

    def test_dry_run_merge_via_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed_path = Path(tmp) / "seed.json"
            seed_path.write_text(
                json.dumps({"version": 1, "entries": [_entry("a", "A")]}),
                encoding="utf-8",
            )
            patch_path = Path(tmp) / "patch.json"
            patch_path.write_text(
                json.dumps({"entries": [_entry("b", "B")]}),
                encoding="utf-8",
            )
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            patch = json.loads(patch_path.read_text(encoding="utf-8"))["entries"]
            merged, report = merge_seed(seed, patch, fill_missing_display=False)
            self.assertEqual(len(merged["entries"]), 2)
            self.assertEqual(report["added_count"], 1)
            # Original file unchanged when not written
            original = json.loads(seed_path.read_text(encoding="utf-8"))
            self.assertEqual(len(original["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
