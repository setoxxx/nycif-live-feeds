#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_supplemental_row_corrections import run  # noqa: E402
from scripts.coverage_gap_utils import overlap_key  # noqa: E402


class SupplementalRowCorrectionsTests(unittest.TestCase):
    def test_overlap_key_decodes_html_entities(self) -> None:
        plain = overlap_key("Just for Kids: Uncle Tony's Reptile Show", "2026-07-18T11:00 am")
        encoded = overlap_key("Just for Kids: Uncle Tony&#8217;s Reptile Show", "2026-07-18T11:00 am")
        self.assertEqual(plain, encoded)
        self.assertEqual(plain, "just for kids uncle tony s reptile show|2026-07-18")

    def test_apply_corrections_updates_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "queue.json"
            corrections_path = Path(tmp) / "corrections.json"
            report_path = Path(tmp) / "report.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "approval_queue": [
                            {
                                "review_rank": 15,
                                "overlap_key": "just for kids uncle tony 8217 s reptile show|2026-07-18",
                                "title": "Just for Kids: Uncle Tony&#8217;s Reptile Show",
                                "manual_review_status": "approved",
                                "proposed_lat": 40.5964589,
                                "proposed_lng": -73.9193055,
                            },
                            {
                                "review_rank": 2427,
                                "overlap_key": "just for kids uncle tony s reptile show|2026-07-18",
                                "title": "Just for Kids: Uncle Tony's Reptile Show",
                                "manual_review_status": "approved",
                                "proposed_lat": 40.5964589,
                                "proposed_lng": -73.9193055,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            corrections_path.write_text(
                json.dumps(
                    {
                        "corrections": [
                            {
                                "review_rank": 2427,
                                "manual_review_status": "rejected",
                                "approval_decision_reason": "duplicate",
                            },
                            {
                                "review_rank": 15,
                                "title": "Just for Kids: Uncle Tony's Reptile Show",
                                "overlap_key": "just for kids uncle tony s reptile show|2026-07-18",
                                "proposed_lat": 40.6074677,
                                "proposed_lng": -73.9391634,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            import scripts.apply_supplemental_row_corrections as mod

            original_queue = mod.APPROVAL_QUEUE_PATH
            original_report = mod.REPORT_PATH
            mod.APPROVAL_QUEUE_PATH = queue_path
            mod.REPORT_PATH = report_path
            try:
                self.assertEqual(run(corrections_path=corrections_path, dry_run=False), 0)
            finally:
                mod.APPROVAL_QUEUE_PATH = original_queue
                mod.REPORT_PATH = original_report

            payload = json.loads(queue_path.read_text(encoding="utf-8"))
            rows = {row["review_rank"]: row for row in payload["approval_queue"]}
            self.assertEqual(rows[2427]["manual_review_status"], "rejected")
            self.assertEqual(rows[15]["overlap_key"], "just for kids uncle tony s reptile show|2026-07-18")
            self.assertAlmostEqual(float(rows[15]["proposed_lat"]), 40.6074677)
            self.assertAlmostEqual(float(rows[15]["proposed_lng"]), -73.9391634)


if __name__ == "__main__":
    unittest.main()
