"""Tests for supplemental coverage-gap review queue builders."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_gps_unfilled_review_report import (  # noqa: E402
    review_guidance,
)
from scripts.coverage_gap_utils import (  # noqa: E402
    overlap_key,
    safety_fields,
    valid_nyc_lat_lng,
)


class CoverageGapUtilsTests(unittest.TestCase):
    def test_valid_nyc_lat_lng(self) -> None:
        self.assertTrue(valid_nyc_lat_lng(40.7, -74.0))
        self.assertFalse(valid_nyc_lat_lng(30.0, -74.0))

    def test_overlap_key(self) -> None:
        self.assertEqual(overlap_key("Summer Jam", "2026-07-13T09:00:00"), "summer jam|2026-07-13")

    def test_safety_fields_default_pending(self) -> None:
        fields = safety_fields()
        self.assertEqual(fields["manual_review_status"], "pending")
        self.assertFalse(fields["promotion_allowed"])
        self.assertFalse(fields["public_map_modified"])

    def test_review_guidance_street_segment(self) -> None:
        text = review_guidance({"location_complexity": "street_between_pair"})
        self.assertIn("manual_gps_reference.json", text)


class SupplementalCoverageQueueTests(unittest.TestCase):
    def test_supplemental_script_writes_queues(self) -> None:
        from scripts import build_supplemental_coverage_review_queues as supplemental_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            permit_path = data_dir / "raw_nyc_open_data_snapshot.json"
            calendar_path = data_dir / "nyc_citywide_events_calendar_snapshot.json"
            parks_path = data_dir / "nyc_parks_bigapps_events_snapshot.json"
            permit_path.write_text(
                json.dumps(
                    [
                        {
                            "event_name": "Permit Event",
                            "start_date_time": "2099-01-01T09:00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            calendar_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "Calendar Only",
                            "start_date_time": "2099-01-02T10:00:00.000-04:00",
                            "address": "123 Test Ave",
                            "categories": ["Parks & Recreation"],
                            "boroughs": ["Manhattan"],
                        },
                        {
                            "title": "Shared Parks Calendar",
                            "start_date_time": "2099-01-03T10:00:00.000-04:00",
                            "address": "Central Park",
                            "categories": ["Parks & Recreation"],
                            "boroughs": ["Manhattan"],
                        },
                    ]
                ),
                encoding="utf-8",
            )
            parks_path.write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "title": "Shared Parks Calendar",
                                "start_date_time": "2099-01-03T09:00:00",
                                "location": "Central Park",
                                "lat": 40.7812,
                                "lng": -73.9665,
                            },
                            {
                                "title": "Parks Only Event",
                                "start_date_time": "2099-01-04T09:00:00",
                                "location": "Prospect Park",
                                "lat": 40.6602,
                                "lng": -73.9690,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            originals = {
                "PERMIT_SNAPSHOT": supplemental_mod.PERMIT_SNAPSHOT,
                "CALENDAR_SNAPSHOT": supplemental_mod.CALENDAR_SNAPSHOT,
                "PARKS_SNAPSHOT": supplemental_mod.PARKS_SNAPSHOT,
                "CALENDAR_QUEUE_JSON": supplemental_mod.CALENDAR_QUEUE_JSON,
                "CALENDAR_QUEUE_CSV": supplemental_mod.CALENDAR_QUEUE_CSV,
                "CALENDAR_QUEUE_REPORT": supplemental_mod.CALENDAR_QUEUE_REPORT,
                "PARKS_QUEUE_JSON": supplemental_mod.PARKS_QUEUE_JSON,
                "PARKS_QUEUE_CSV": supplemental_mod.PARKS_QUEUE_CSV,
                "PARKS_QUEUE_REPORT": supplemental_mod.PARKS_QUEUE_REPORT,
                "COORD_PROPOSALS_JSON": supplemental_mod.COORD_PROPOSALS_JSON,
                "COORD_PROPOSALS_REPORT": supplemental_mod.COORD_PROPOSALS_REPORT,
            }
            try:
                supplemental_mod.PERMIT_SNAPSHOT = permit_path
                supplemental_mod.CALENDAR_SNAPSHOT = calendar_path
                supplemental_mod.PARKS_SNAPSHOT = parks_path
                supplemental_mod.CALENDAR_QUEUE_JSON = data_dir / "supplemental_calendar_only_review_queue.json"
                supplemental_mod.CALENDAR_QUEUE_CSV = data_dir / "supplemental_calendar_only_review_queue.csv"
                supplemental_mod.CALENDAR_QUEUE_REPORT = data_dir / "supplemental_calendar_only_review_queue_report.json"
                supplemental_mod.PARKS_QUEUE_JSON = data_dir / "supplemental_parks_only_review_queue.json"
                supplemental_mod.PARKS_QUEUE_CSV = data_dir / "supplemental_parks_only_review_queue.csv"
                supplemental_mod.PARKS_QUEUE_REPORT = data_dir / "supplemental_parks_only_review_queue_report.json"
                supplemental_mod.COORD_PROPOSALS_JSON = data_dir / "calendar_parks_coord_match_proposals.json"
                supplemental_mod.COORD_PROPOSALS_REPORT = data_dir / "calendar_parks_coord_match_proposals_report.json"

                self.assertEqual(supplemental_mod.main(), 0)
                calendar_report = json.loads(
                    supplemental_mod.CALENDAR_QUEUE_REPORT.read_text(encoding="utf-8")
                )
                parks_report = json.loads(supplemental_mod.PARKS_QUEUE_REPORT.read_text(encoding="utf-8"))
                coord_report = json.loads(supplemental_mod.COORD_PROPOSALS_REPORT.read_text(encoding="utf-8"))
                self.assertEqual(calendar_report["queue_count"], 2)
                self.assertEqual(calendar_report["parks_title_date_match_count"], 1)
                self.assertEqual(parks_report["queue_count"], 2)
                self.assertEqual(coord_report["proposal_count"], 1)
            finally:
                for name, value in originals.items():
                    setattr(supplemental_mod, name, value)


class UnfilledGpsReviewTests(unittest.TestCase):
    def test_unfilled_report_script(self) -> None:
        from scripts import build_gps_unfilled_review_report as unfilled_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            filled_path = data_dir / "gps_review_geocoding_filled_proposals.json"
            filled_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "group_key": "manhattan|test street",
                                "display_location": "TEST STREET between A and B",
                                "borough": "Manhattan",
                                "event_count": 2,
                                "priority_score": 10,
                                "location_complexity": "street_between_pair",
                                "proposal_status": "unfilled_pending_geocoder",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            originals = {
                "FILLED_PROPOSALS_PATH": unfilled_mod.FILLED_PROPOSALS_PATH,
                "UNFILLED_REPORT_PATH": unfilled_mod.UNFILLED_REPORT_PATH,
                "UNFILLED_QUEUE_JSON": unfilled_mod.UNFILLED_QUEUE_JSON,
                "UNFILLED_QUEUE_CSV": unfilled_mod.UNFILLED_QUEUE_CSV,
                "MANUAL_REFERENCE_TEMPLATE_PATH": unfilled_mod.MANUAL_REFERENCE_TEMPLATE_PATH,
            }
            try:
                unfilled_mod.FILLED_PROPOSALS_PATH = filled_path
                unfilled_mod.UNFILLED_REPORT_PATH = data_dir / "gps_review_geocoding_unfilled_report.json"
                unfilled_mod.UNFILLED_QUEUE_JSON = data_dir / "gps_review_geocoding_unfilled_review_queue.json"
                unfilled_mod.UNFILLED_QUEUE_CSV = data_dir / "gps_review_geocoding_unfilled_review_queue.csv"
                unfilled_mod.MANUAL_REFERENCE_TEMPLATE_PATH = data_dir / "manual_gps_reference.template.json"
                self.assertEqual(unfilled_mod.main(), 0)
                report = json.loads(unfilled_mod.UNFILLED_REPORT_PATH.read_text(encoding="utf-8"))
                self.assertEqual(report["unfilled_count"], 1)
                self.assertEqual(report["street_between_pair_count"], 1)
            finally:
                for name, value in originals.items():
                    setattr(unfilled_mod, name, value)


class CoverageGapFindingsTests(unittest.TestCase):
    def test_findings_script_writes_artifacts(self) -> None:
        from scripts import build_coverage_gap_review_findings as findings_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "gps_review_geocoding_unfilled_review_queue.json").write_text(
                json.dumps(
                    {
                        "review_queue": [
                            {
                                "group_key": "manhattan|test street",
                                "display_location": "TEST STREET between A and B",
                                "borough": "Manhattan",
                                "event_count": 2,
                                "priority_score": 10,
                                "location_complexity": "street_between_pair",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "supplemental_calendar_only_review_queue.json").write_text(
                json.dumps(
                    {
                        "review_queue": [
                            {
                                "overlap_key": "park yoga|2099-01-01",
                                "title": "Park Yoga",
                                "start_date_time": "2099-01-01T10:00:00",
                                "boroughs": ["Manhattan"],
                                "categories": ["Parks & Recreation"],
                                "parks_title_date_match": True,
                                "proposed_lat": 40.7,
                                "proposed_lng": -74.0,
                                "review_rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "supplemental_parks_only_review_queue.json").write_text(
                json.dumps(
                    {
                        "review_queue": [
                            {
                                "overlap_key": "unique hike|2099-01-02",
                                "title": "Unique Hike",
                                "start_date_time": "2099-01-02T09:00:00",
                                "location": "Central Park",
                                "lat": 40.7812,
                                "lng": -73.9665,
                                "calendar_title_date_match": False,
                                "review_rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            facility_ref = data_dir / "nyc_parks_facility_reference.json"
            parks_snapshot = data_dir / "nyc_parks_bigapps_events_snapshot.json"
            location_cache = data_dir / "location_cache.json"
            facility_ref.write_text(json.dumps({"facilities": []}), encoding="utf-8")
            parks_snapshot.write_text(json.dumps({"events": []}), encoding="utf-8")
            location_cache.write_text(json.dumps({"entries": {}}), encoding="utf-8")

            originals = {
                "UNFILLED_QUEUE": findings_mod.UNFILLED_QUEUE,
                "FACILITY_REF": findings_mod.FACILITY_REF,
                "PARKS_SNAPSHOT": findings_mod.PARKS_SNAPSHOT,
                "LOCATION_CACHE": findings_mod.LOCATION_CACHE,
                "GPS_FINDINGS": findings_mod.GPS_FINDINGS,
                "CALENDAR_QUEUE": findings_mod.CALENDAR_QUEUE,
                "CALENDAR_FINDINGS": findings_mod.CALENDAR_FINDINGS,
                "CALENDAR_PRIORITY_CSV": findings_mod.CALENDAR_PRIORITY_CSV,
                "PARKS_QUEUE": findings_mod.PARKS_QUEUE,
                "PARKS_FINDINGS": findings_mod.PARKS_FINDINGS,
            }
            try:
                findings_mod.UNFILLED_QUEUE = data_dir / "gps_review_geocoding_unfilled_review_queue.json"
                findings_mod.FACILITY_REF = facility_ref
                findings_mod.PARKS_SNAPSHOT = parks_snapshot
                findings_mod.LOCATION_CACHE = location_cache
                findings_mod.CALENDAR_QUEUE = data_dir / "supplemental_calendar_only_review_queue.json"
                findings_mod.PARKS_QUEUE = data_dir / "supplemental_parks_only_review_queue.json"
                findings_mod.GPS_FINDINGS = data_dir / "gps_unfilled_review_findings.json"
                findings_mod.CALENDAR_FINDINGS = data_dir / "supplemental_calendar_only_review_findings.json"
                findings_mod.CALENDAR_PRIORITY_CSV = data_dir / "supplemental_calendar_only_priority_review.csv"
                findings_mod.PARKS_FINDINGS = data_dir / "supplemental_parks_only_review_findings.json"
                self.assertEqual(findings_mod.main(), 0)
                gps = json.loads(findings_mod.GPS_FINDINGS.read_text(encoding="utf-8"))
                cal = json.loads(findings_mod.CALENDAR_FINDINGS.read_text(encoding="utf-8"))
                parks = json.loads(findings_mod.PARKS_FINDINGS.read_text(encoding="utf-8"))
                self.assertEqual(gps["input_count"], 1)
                self.assertEqual(cal["likely_valid_parks_overlap_count"], 1)
                self.assertEqual(parks["high_value_unique_events_count"], 1)
            finally:
                for name, value in originals.items():
                    setattr(findings_mod, name, value)


if __name__ == "__main__":
    unittest.main()
