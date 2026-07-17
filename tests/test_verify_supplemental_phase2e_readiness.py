"""Tests for supplemental Phase 2E readiness verification."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_supplemental_phase2e_readiness import verify_dry_run, verify_export


class SupplementalPhase2eReadinessTests(unittest.TestCase):
    def test_committed_export_and_dry_run_pass(self) -> None:
        export = json.loads((ROOT / "data/supplemental_approved_export_feed.json").read_text(encoding="utf-8"))
        dry_run = json.loads(
            (ROOT / "data/reports/supplemental_phase2e_promotion_dry_run_report.json").read_text(encoding="utf-8")
        )
        export_errors = verify_export(export)
        dry_run_errors = verify_dry_run(dry_run)
        self.assertEqual(export.get("export_event_count"), 3566)
        self.assertEqual([], export_errors, export_errors)
        self.assertEqual([], dry_run_errors, dry_run_errors)


if __name__ == "__main__":
    unittest.main()
