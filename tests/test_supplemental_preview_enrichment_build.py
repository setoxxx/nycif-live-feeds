"""Tests for supplemental preview enrichment build scripts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_supplemental_cultural_anniversary_staging import build_anniversary_staging
from scripts.build_supplemental_press_geofence_staging import build_press_geofence_staging


class SupplementalPreviewEnrichmentBuildTests(unittest.TestCase):
    def test_anniversary_staging_from_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            reports_dir = data_dir / "reports"
            data_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            export = {
                "artifact_type": "supplemental_approved_export_feed",
                "events": [
                    {
                        "overlap_key": "x|2026-07-18",
                        "title": "15th Annual Parade",
                        "date": "2026-07-18",
                        "lat": 40.75,
                        "lng": -73.98,
                    },
                    {"overlap_key": "y|2026-07-18", "title": "Pool Swim", "date": "2026-07-18"},
                ],
            }
            (data_dir / "supplemental_approved_export_feed.json").write_text(
                json.dumps(export), encoding="utf-8"
            )

            import scripts.build_supplemental_cultural_anniversary_staging as anni_mod

            original_data = anni_mod.DATA_DIR
            original_export = anni_mod.EXPORT_PATH
            original_staging = anni_mod.STAGING_PATH
            original_report = anni_mod.REPORT_PATH
            try:
                anni_mod.DATA_DIR = data_dir
                anni_mod.EXPORT_PATH = data_dir / "supplemental_approved_export_feed.json"
                anni_mod.STAGING_PATH = data_dir / "supplemental_cultural_anniversary_staging.json"
                anni_mod.REPORT_PATH = reports_dir / "supplemental_cultural_anniversary_report.json"
                report = build_anniversary_staging()
                self.assertTrue(report["qa_pass"])
                self.assertEqual(report["anniversary_row_count"], 1)
            finally:
                anni_mod.DATA_DIR = original_data
                anni_mod.EXPORT_PATH = original_export
                anni_mod.STAGING_PATH = original_staging
                anni_mod.REPORT_PATH = original_report

    def test_geofence_staging_from_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            reports_dir = data_dir / "reports"
            data_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            export = {
                "artifact_type": "supplemental_approved_export_feed",
                "events": [
                    {
                        "overlap_key": "x|2026-07-18",
                        "title": "Pool Swim",
                        "date": "2026-07-18",
                        "lat": 40.705,
                        "lng": -74.005,
                    }
                ],
            }
            precinct_ref = {
                "artifact_type": "nypd_precinct_boundaries_reference",
                "precincts": [
                    {
                        "precinct": "99",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71], [-74.01, 40.70]]],
                        },
                    }
                ],
            }
            (data_dir / "supplemental_approved_export_feed.json").write_text(
                json.dumps(export), encoding="utf-8"
            )
            (data_dir / "nypd_precinct_boundaries_reference.json").write_text(
                json.dumps(precinct_ref), encoding="utf-8"
            )

            import scripts.build_supplemental_press_geofence_staging as geo_mod

            original_data = geo_mod.DATA_DIR
            original_export = geo_mod.EXPORT_PATH
            original_precinct = geo_mod.PRECINCT_PATH
            original_staging = geo_mod.STAGING_PATH
            original_report = geo_mod.REPORT_PATH
            try:
                geo_mod.DATA_DIR = data_dir
                geo_mod.EXPORT_PATH = data_dir / "supplemental_approved_export_feed.json"
                geo_mod.PRECINCT_PATH = data_dir / "nypd_precinct_boundaries_reference.json"
                geo_mod.STAGING_PATH = data_dir / "supplemental_press_geofence_staging.json"
                geo_mod.REPORT_PATH = reports_dir / "supplemental_press_geofence_report.json"
                report = build_press_geofence_staging()
                self.assertTrue(report["qa_pass"])
                self.assertEqual(report["geofence_row_count"], 1)
            finally:
                geo_mod.DATA_DIR = original_data
                geo_mod.EXPORT_PATH = original_export
                geo_mod.PRECINCT_PATH = original_precinct
                geo_mod.STAGING_PATH = original_staging
                geo_mod.REPORT_PATH = original_report


if __name__ == "__main__":
    unittest.main()
