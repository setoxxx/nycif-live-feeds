#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import classify_record, match_recurring_registry, resolve_coords  # noqa: E402
from project_events_discovery_v02 import (  # noqa: E402
    SEASON_END_DATE,
    SEASON_START_DATE,
    build_base_event,
    event_overlaps_season,
)


MOUNT_CARMEL_ROW = {
    "event_name": "Our Lady of Mt. Carmel Church Feast",
    "event_type": "Street Festival",
    "event_borough": "Brooklyn",
    "event_location": (
        "HAVEMEYER STREET between METROPOLITAN AVENUE and NORTH    9 STREET,  "
        "WITHERS STREET between NORTH    9 STREET and UNION AVENUE,  "
        "NORTH    8 STREET between ROEBLING STREET and MEEKER AVENUE"
    ),
    "source_dataset": "tvpp-9vvx",
    "source_event_id": "906428",
    "start_date_time": "2026-07-08T19:00:00.000",
    "end_date_time": "2026-07-19T20:00:00.000",
}


class UnstagedOpenDataIntakeTests(unittest.TestCase):
    def test_mount_carmel_classifies_as_civic_feast(self) -> None:
        classified = classify_record(MOUNT_CARMEL_ROW)
        self.assertEqual(classified["category"], "civic")
        self.assertIn("feast", classified["tags"])

    def test_mount_carmel_matches_recurring_registry(self) -> None:
        registry, _signals, _reasons = match_recurring_registry(MOUNT_CARMEL_ROW)
        self.assertIsNotNone(registry)
        self.assertEqual(registry["key"], "our-lady-of-mount-carmel-feast")

    def test_mount_carmel_overlaps_season_window(self) -> None:
        self.assertTrue(event_overlaps_season(MOUNT_CARMEL_ROW, SEASON_START_DATE, SEASON_END_DATE))

    def test_mount_carmel_builds_map_ready_multi_day_event(self) -> None:
        event = build_base_event(
            MOUNT_CARMEL_ROW,
            data_layer="review_supplemental",
            index=0,
            production_feed=False,
            current_major_keys=set(),
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["category"], "civic")
        self.assertEqual(event["end_date_time"], "2026-07-19T20:00:00.000")
        self.assertEqual(event["nycif"]["coordinate_status"], "map_ready")
        self.assertTrue(event["nycif"]["is_major"])
        lat, lng, ok = resolve_coords(MOUNT_CARMEL_ROW)
        self.assertTrue(ok)
        self.assertAlmostEqual(event["latitude"], lat, places=5)
        self.assertAlmostEqual(event["longitude"], lng, places=5)


if __name__ == "__main__":
    unittest.main()
