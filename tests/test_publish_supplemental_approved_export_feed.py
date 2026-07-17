"""Tests for supplemental approved export feed publish script."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.publish_supplemental_approved_export_feed import (  # noqa: E402
    publish_export_feed,
    validate_export_payload,
)


class PublishSupplementalApprovedExportFeedTests(unittest.TestCase):
    def test_validate_rejects_non_export_artifact(self) -> None:
        with self.assertRaises(ValueError):
            validate_export_payload({"artifact_type": "gps_manual_approval_queue"})

    def test_validate_rejects_production_feed(self) -> None:
        with self.assertRaises(ValueError):
            validate_export_payload(
                {
                    "artifact_type": "supplemental_approved_export_feed",
                    "production_feed": True,
                    "events": [],
                }
            )

    def test_publish_copies_export_to_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            reports_dir = data_dir / "reports"
            dist_dir = root / "dist"
            data_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)

            export_payload = {
                "artifact_type": "supplemental_approved_export_feed",
                "production_feed": False,
                "promotion_allowed": False,
                "export_event_count": 2,
                "approved_queue_count": 2,
                "events": [
                    {"overlap_key": "a|2026-07-01", "manual_review_status": "approved"},
                    {"overlap_key": "b|2026-07-02", "manual_review_status": "approved"},
                ],
            }
            export_path = data_dir / "supplemental_approved_export_feed.json"
            export_path.write_text(json.dumps(export_payload), encoding="utf-8")

            import scripts.publish_supplemental_approved_export_feed as publish_mod

            original_root = publish_mod.ROOT
            original_data = publish_mod.DATA_DIR
            original_export = publish_mod.EXPORT_PATH
            original_dist = publish_mod.DIST_DIR
            original_dist_export = publish_mod.DIST_EXPORT_PATH
            original_report = publish_mod.REPORT_PATH
            try:
                publish_mod.ROOT = root
                publish_mod.DATA_DIR = data_dir
                publish_mod.EXPORT_PATH = export_path
                publish_mod.DIST_DIR = dist_dir
                publish_mod.DIST_EXPORT_PATH = dist_dir / "supplemental_approved_export_feed.json"
                publish_mod.REPORT_PATH = reports_dir / "supplemental_approved_export_publish_report.json"

                report = publish_export_feed()
                self.assertTrue(report["qa_pass"])
                self.assertTrue((dist_dir / "supplemental_approved_export_feed.json").exists())
                copied = json.loads(
                    (dist_dir / "supplemental_approved_export_feed.json").read_text(encoding="utf-8")
                )
                self.assertEqual(copied["export_event_count"], 2)
            finally:
                publish_mod.ROOT = original_root
                publish_mod.DATA_DIR = original_data
                publish_mod.EXPORT_PATH = original_export
                publish_mod.DIST_DIR = original_dist
                publish_mod.DIST_EXPORT_PATH = original_dist_export
                publish_mod.REPORT_PATH = original_report


if __name__ == "__main__":
    unittest.main()
