from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts import build_maplibre_reader_safe_v03 as reader_safe


class P0EventReaderVisibilityTests(unittest.TestCase):
    def jamaica_event(self) -> dict:
        return {
            "id": "tvpp-9vvx:906790@2026-08-08",
            "title": "Jamaica Rising Day Parade",
            "category": "civic",
            "borough": "Brooklyn",
            "location": "Ocean Avenue between Church Avenue and Lincoln Road",
            "start_date_time": "2026-08-08T11:00:00.000",
            "end_date_time": "2026-08-08T17:00:00.000",
            "timezone": "America/New_York",
            "event_role": "public_event",
            "parent_event_id": None,
            "source": {"dataset": "tvpp-9vvx", "source_event_id": "906790"},
            "nycif": {
                "map_eligibility_state": "REVIEW_REQUIRED",
                "certified_pin": False,
                "location_authority": "projector_v3_semantic_map_decision",
                "display_disposition": "standalone_public_event",
            },
        }

    def synthetic_exact_event(self) -> dict:
        return {
            "id": "synthetic:exact-marker@2026-08-09",
            "title": "Synthetic Exact Marker Fixture",
            "category": "test",
            "borough": "Manhattan",
            "location": "Synthetic certified location",
            "start_date_time": "2026-08-09T12:00:00.000",
            "end_date_time": "2026-08-09T13:00:00.000",
            "timezone": "America/New_York",
            "event_role": "public_event",
            "parent_event_id": None,
            "source": {"dataset": "synthetic-test", "source_event_id": "exact-1"},
            "latitude": 40.7500,
            "longitude": -73.9900,
            "location_evidence": {
                "tier": "certified_street_segment",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "synthetic_regression_fixture",
            },
            "nycif": {
                "map_eligibility_state": "MAP_READY",
                "certified_pin": True,
                "location_authority": "projector_v3_semantic_map_decision",
                "display_disposition": "standalone_public_event",
            },
        }

    def test_jamaica_rising_remains_reader_visible_without_exact_pin(self) -> None:
        event = self.jamaica_event()
        self.assertTrue(reader_safe.reader_visible_event(event))
        self.assertTrue(
            reader_safe.event_in_reader_window(
                event,
                date(2026, 8, 8),
                date(2026, 8, 15),
            )
        )
        feature = reader_safe.feature(event, exact_marker=False)
        self.assertIsNone(feature["geometry"])
        self.assertEqual(feature["properties"]["source_event_id"], "906790")
        self.assertEqual(feature["properties"]["title"], "Jamaica Rising Day Parade")
        self.assertFalse(feature["properties"]["certified_pin"])
        self.assertEqual(feature["properties"]["map_eligibility_state"], "REVIEW_REQUIRED")

    def test_exact_marker_stays_a_point_only_when_explicitly_requested(self) -> None:
        event = self.synthetic_exact_event()
        feature = reader_safe.feature(event, exact_marker=True)
        self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertEqual(feature["geometry"]["coordinates"], [-73.99, 40.75])
        self.assertTrue(feature["properties"]["certified_pin"])

    def test_late_same_day_event_remains_in_today_window(self) -> None:
        event = {
            "id": "synthetic:late-same-day@2026-08-08",
            "title": "Synthetic Late Same-Day Permit",
            "category": "test",
            "borough": "Queens",
            "location": "Reader-visible text-only fixture",
            "start_date_time": "2026-08-08T23:30:00.000",
            "end_date_time": "2026-08-08T23:59:00.000",
            "timezone": "America/New_York",
            "event_role": "public_event",
            "parent_event_id": None,
            "source": {"dataset": "synthetic-test", "source_event_id": "late-1"},
            "nycif": {
                "map_eligibility_state": "LIST_ONLY",
                "certified_pin": False,
                "location_authority": "projector_v3_semantic_map_decision",
                "display_disposition": "standalone_public_event",
            },
        }
        self.assertTrue(reader_safe.reader_visible_event(event))
        self.assertTrue(
            reader_safe.event_in_reader_window(
                event,
                date(2026, 8, 8),
                date(2026, 8, 15),
            )
        )
        feature = reader_safe.feature(event, exact_marker=False)
        self.assertIsNone(feature["geometry"])
        self.assertEqual(feature["properties"]["source_event_id"], "late-1")

    def test_supporting_records_do_not_become_reader_events(self) -> None:
        event = self.jamaica_event()
        event["event_role"] = "street_closure"
        self.assertFalse(reader_safe.reader_visible_event(event))

    def test_old_event_outside_reader_window_is_not_carried(self) -> None:
        event = self.jamaica_event()
        event["start_date_time"] = "2026-07-01T11:00:00.000"
        event["end_date_time"] = "2026-07-01T17:00:00.000"
        self.assertFalse(
            reader_safe.event_in_reader_window(
                event,
                date(2026, 8, 8),
                date(2026, 8, 15),
            )
        )


if __name__ == "__main__":
    unittest.main()
