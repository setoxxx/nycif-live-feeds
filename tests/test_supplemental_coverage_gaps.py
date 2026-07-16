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


class SupplementalStagingFeedTests(unittest.TestCase):
    def test_staging_feed_merges_queues(self) -> None:
        from scripts import build_supplemental_events_staging_feed as staging_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            calendar_queue = [
                {
                    "overlap_key": "cal event|2099-01-02",
                    "title": "Cal Event",
                    "start_date_time": "2099-01-02T10:00:00",
                    "address": "123 Test Ave",
                    "boroughs": ["Manhattan"],
                    "source_event_id": "c1",
                    "parks_title_date_match": False,
                }
            ]
            parks_queue = [
                {
                    "overlap_key": "parks event|2099-01-03",
                    "title": "Parks Event",
                    "start_date_time": "2099-01-03T10:00:00",
                    "location": "Prospect Park",
                    "borough": "Brooklyn",
                    "lat": 40.66,
                    "lng": -73.97,
                    "has_coordinates": True,
                    "source_event_id": "p1",
                }
            ]
            originals = {
                "CALENDAR_QUEUE": staging_mod.CALENDAR_QUEUE,
                "PARKS_QUEUE": staging_mod.PARKS_QUEUE,
                "FEED_PATH": staging_mod.FEED_PATH,
                "MANIFEST_PATH": staging_mod.MANIFEST_PATH,
                "REPORT_PATH": staging_mod.REPORT_PATH,
            }
            staging_mod.CALENDAR_QUEUE = data_dir / "supplemental_calendar_only_review_queue.json"
            staging_mod.PARKS_QUEUE = data_dir / "supplemental_parks_only_review_queue.json"
            staging_mod.FEED_PATH = data_dir / "supplemental_events_staging_feed.json"
            staging_mod.MANIFEST_PATH = data_dir / "supplemental_events_staging_manifest.json"
            staging_mod.REPORT_PATH = data_dir / "supplemental_events_staging_report.json"
            staging_mod.CALENDAR_QUEUE.write_text(json.dumps(calendar_queue), encoding="utf-8")
            staging_mod.PARKS_QUEUE.write_text(json.dumps(parks_queue), encoding="utf-8")
            try:
                self.assertEqual(staging_mod.main(), 0)
                feed = json.loads(staging_mod.FEED_PATH.read_text(encoding="utf-8"))
                report = json.loads(staging_mod.REPORT_PATH.read_text(encoding="utf-8"))
                self.assertEqual(report["event_count"], 2)
                self.assertFalse(feed["promotion_allowed"])
                intake_types = {row["intake_type"] for row in feed["events"]}
                self.assertEqual(intake_types, {"calendar_only", "parks_only"})
            finally:
                for name, value in originals.items():
                    setattr(staging_mod, name, value)


class SupplementalManualApprovalTests(unittest.TestCase):
    def test_m11_manual_approval_package(self) -> None:
        from scripts import build_supplemental_manual_approval_queue as queue_mod
        from scripts import build_supplemental_manual_review_sheet as sheet_mod
        from scripts import validate_supplemental_manual_approvals as validate_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            feed_path = data_dir / "supplemental_events_staging_feed.json"
            feed_path.write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "overlap_key": "park hike|2099-01-02",
                                "intake_type": "parks_only",
                                "title": "Park Hike",
                                "start_date_time": "2099-01-02T09:00:00",
                                "date": "2099-01-02",
                                "display_location": "Central Park",
                                "borough": "Manhattan",
                                "proposed_lat": 40.7812,
                                "proposed_lng": -73.9665,
                                "geocoder_source": "nyc_parks_bigapps_events_snapshot",
                                "geocoder_confidence": "high",
                                "confidence_reason": "test",
                                "calendar_title_date_match": False,
                                "source_event_id": "p1",
                            },
                            {
                                "overlap_key": "cal fair|2099-01-03",
                                "intake_type": "calendar_only",
                                "title": "Cal Fair",
                                "start_date_time": "2099-01-03T10:00:00",
                                "date": "2099-01-03",
                                "display_location": "123 Main St",
                                "borough": "Brooklyn",
                                "proposed_lat": None,
                                "proposed_lng": None,
                                "parks_title_date_match": False,
                                "source_event_id": "c1",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            originals = {
                "STAGING_FEED_PATH": queue_mod.STAGING_FEED_PATH,
                "APPROVAL_QUEUE_PATH": queue_mod.APPROVAL_QUEUE_PATH,
                "APPROVAL_QUEUE_REPORT_PATH": queue_mod.APPROVAL_QUEUE_REPORT_PATH,
            }
            sheet_originals = {
                "APPROVAL_QUEUE_PATH": sheet_mod.APPROVAL_QUEUE_PATH,
                "REVIEW_SHEET_JSON_PATH": sheet_mod.REVIEW_SHEET_JSON_PATH,
                "REVIEW_SHEET_CSV_PATH": sheet_mod.REVIEW_SHEET_CSV_PATH,
                "REVIEW_SHEET_REPORT_PATH": sheet_mod.REVIEW_SHEET_REPORT_PATH,
            }
            validate_originals = {
                "APPROVAL_QUEUE_PATH": validate_mod.APPROVAL_QUEUE_PATH,
                "VALIDATION_REPORT_PATH": validate_mod.VALIDATION_REPORT_PATH,
            }
            try:
                queue_mod.STAGING_FEED_PATH = feed_path
                queue_mod.APPROVAL_QUEUE_PATH = data_dir / "supplemental_manual_approval_queue.json"
                queue_mod.APPROVAL_QUEUE_REPORT_PATH = data_dir / "supplemental_manual_approval_queue_report.json"
                self.assertEqual(queue_mod.main(), 0)
                queue_report = json.loads(queue_mod.APPROVAL_QUEUE_REPORT_PATH.read_text(encoding="utf-8"))
                self.assertEqual(queue_report["approval_queue_count"], 2)
                self.assertEqual(queue_report["pending_count"], 2)
                self.assertTrue(queue_report["qa_pass"])

                validate_mod.APPROVAL_QUEUE_PATH = queue_mod.APPROVAL_QUEUE_PATH
                validate_mod.VALIDATION_REPORT_PATH = data_dir / "supplemental_manual_approval_validation_report.json"
                self.assertEqual(validate_mod.main(), 0)
                validation = json.loads(validate_mod.VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
                self.assertTrue(validation["qa_pass"])

                sheet_mod.APPROVAL_QUEUE_PATH = queue_mod.APPROVAL_QUEUE_PATH
                sheet_mod.REVIEW_SHEET_JSON_PATH = data_dir / "supplemental_manual_approval_review_sheet.json"
                sheet_mod.REVIEW_SHEET_CSV_PATH = data_dir / "supplemental_manual_approval_review_sheet.csv"
                sheet_mod.REVIEW_SHEET_REPORT_PATH = data_dir / "supplemental_manual_approval_review_sheet_report.json"
                self.assertEqual(sheet_mod.main(), 0)
                sheet_report = json.loads(sheet_mod.REVIEW_SHEET_REPORT_PATH.read_text(encoding="utf-8"))
                self.assertEqual(sheet_report["review_sheet_count"], 2)
            finally:
                for name, value in originals.items():
                    setattr(queue_mod, name, value)
                for name, value in sheet_originals.items():
                    setattr(sheet_mod, name, value)
                for name, value in validate_originals.items():
                    setattr(validate_mod, name, value)


class SupplementalDecisionsPatchTests(unittest.TestCase):
    def test_apply_decisions_patch_by_review_rank(self) -> None:
        from scripts import apply_supplemental_manual_approval_decisions as apply_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            queue_path = data_dir / "supplemental_manual_approval_queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "approval_queue": [
                            {
                                "review_rank": 1,
                                "overlap_key": "active hike|2099-01-01",
                                "title": "Active Hike",
                                "manual_review_status": "pending",
                                "promotion_allowed": False,
                            },
                            {
                                "review_rank": 2,
                                "overlap_key": "canceled yoga|2099-01-02",
                                "title": "CANCELED: Yoga",
                                "manual_review_status": "pending",
                                "promotion_allowed": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            decisions_path = data_dir / "supplemental_manual_approval_decisions.json"
            decisions_path.write_text(
                json.dumps(
                    {
                        "manual_reviewer": "test-reviewer",
                        "decisions": [
                            {
                                "review_rank": 2,
                                "manual_review_status": "rejected",
                                "approval_decision_reason": "Canceled in title.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            originals = {
                "APPROVAL_QUEUE_PATH": apply_mod.APPROVAL_QUEUE_PATH,
                "DECISIONS_PATH": apply_mod.DECISIONS_PATH,
                "DECISIONS_REPORT_PATH": apply_mod.DECISIONS_REPORT_PATH,
            }
            try:
                apply_mod.APPROVAL_QUEUE_PATH = queue_path
                apply_mod.DECISIONS_PATH = decisions_path
                apply_mod.DECISIONS_REPORT_PATH = data_dir / "supplemental_manual_approval_decisions_report.json"
                self.assertEqual(
                    apply_mod.run(
                        decisions_path=decisions_path,
                        dry_run=False,
                    ),
                    0,
                )
                updated = json.loads(queue_path.read_text(encoding="utf-8"))["approval_queue"]
                self.assertEqual(updated[0]["manual_review_status"], "pending")
                self.assertEqual(updated[1]["manual_review_status"], "rejected")
                self.assertEqual(updated[1]["manual_reviewer"], "test-reviewer")
                self.assertFalse(updated[1]["promotion_allowed"])
            finally:
                for name, value in originals.items():
                    setattr(apply_mod, name, value)


if __name__ == "__main__":
    unittest.main()
