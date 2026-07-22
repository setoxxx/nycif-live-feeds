#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_approved_dedupe import (  # noqa: E402
    build_cems_source_lookup,
    dedupe_approved_events,
    dedupe_shared_cems_occurrences,
)


def event(
    source_event_id: str,
    *,
    canonical_id: str | None = None,
    dataset: str = "tvpp-9vvx",
    day: str = "2026-07-22",
    start: str = "18:00:00",
    end: str = "20:00:00",
    location: str = "Chelsea Park Soccer 01",
    latitude: float = 40.74994,
    longitude: float = -74.00073,
    category: str = "sports",
    event_type: str = "Athletic",
) -> dict:
    return {
        "schema_version": "1.0",
        "id": canonical_id or f"{dataset}:{source_event_id}@{day}",
        "event_group_id": canonical_id or f"{dataset}:{source_event_id}@{day}",
        "parent_event_id": None,
        "title": "Soccer - Non Regulation",
        "description": None,
        "category": category,
        "interests": ["sports"],
        "tags": [],
        "event_role": "public_event",
        "significance": "standard",
        "audience": [],
        "start_date_time": f"{day}T{start}-04:00",
        "end_date_time": f"{day}T{end}-04:00",
        "timezone": "America/New_York",
        "borough": "Manhattan",
        "neighborhood": None,
        "location": location,
        "address": None,
        "latitude": latitude,
        "longitude": longitude,
        "source": {"dataset": dataset, "source_event_id": source_event_id, "source_url": None},
        "nycif": {
            "data_layer": "approved_staged",
            "coordinate_status": "map_ready",
            "display_disposition": "standalone_public_event",
            "is_major": False,
            "photo_pick": False,
            "field_default": False,
            "crowd_level": None,
            "priority_score": None,
            "expected_crowd_score": None,
            "event_date": day,
            "event_type": event_type,
            "event_agency": "Parks",
        },
    }


def lookups(events: list[dict], cems_by_id: dict[str, str | None]):
    rows = []
    for item in events:
        source = item["source"]
        cemsid = cems_by_id.get(source["source_event_id"])
        row = {
            "source_dataset": source["dataset"],
            "source_event_id": source["source_event_id"],
            "source_cemsid": cemsid,
            "event_name": item["title"],
        }
        rows.append(row)
    return build_cems_source_lookup({"data/raw_nyc_open_data_snapshot.json": rows})


class SharedCemsOccurrenceDedupeTests(unittest.TestCase):
    def apply(self, events: list[dict], cems_by_id: dict[str, str | None]):
        cems, evidence = lookups(events, cems_by_id)
        return dedupe_shared_cems_occurrences(events, cems, evidence)

    def test_two_member_group(self) -> None:
        events = [event("20"), event("10")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual([item["source"]["source_event_id"] for item in kept], ["10"])
        self.assertEqual(stats["group_count"], 1)
        self.assertEqual(stats["suppressed_projection_count"], 1)

    def test_three_member_group(self) -> None:
        events = [event("30"), event("10"), event("20")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318", "30": "9318"})
        self.assertEqual([item["source"]["source_event_id"] for item in kept], ["10"])
        self.assertEqual(stats["group_member_count"], 3)
        self.assertEqual(stats["suppressed_projection_count"], 2)

    def test_reversed_input_order_is_deterministic(self) -> None:
        forward = [event("10"), event("20"), event("30")]
        reverse = list(reversed(copy.deepcopy(forward)))
        first, first_stats = self.apply(forward, {"10": "9318", "20": "9318", "30": "9318"})
        second, second_stats = self.apply(reverse, {"10": "9318", "20": "9318", "30": "9318"})
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(first_stats["groups"][0]["representative"]["canonical_id"], second_stats["groups"][0]["representative"]["canonical_id"])

    def test_nonnumeric_ids_use_canonical_tiebreak(self) -> None:
        first = event("beta", canonical_id="tvpp-9vvx:a@2026-07-22")
        second = event("alpha", canonical_id="tvpp-9vvx:z@2026-07-22")
        kept, _ = self.apply([first, second], {"alpha": "9318", "beta": "9318"})
        self.assertEqual(kept[0]["source"]["source_event_id"], "beta")

    def test_distinct_dates_remain_separate(self) -> None:
        events = [event("10"), event("20", day="2026-07-23")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_distinct_start_or_end_times_remain_separate(self) -> None:
        events = [event("10"), event("20", start="19:00:00"), event("30", end="21:00:00")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318", "30": "9318"})
        self.assertEqual(len(kept), 3)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_distinct_locations_remain_separate(self) -> None:
        events = [event("10"), event("20", location="Chelsea Park Soccer 02")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_distinct_coordinates_remain_separate(self) -> None:
        events = [event("10"), event("20", latitude=40.749942)]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_distinct_cems_ids_remain_separate(self) -> None:
        events = [event("10"), event("20")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9319"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_different_datasets_remain_separate(self) -> None:
        events = [event("10"), event("20", dataset="other-dataset")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_missing_cems_ids_remain_separate(self) -> None:
        events = [event("10"), event("20")]
        kept, stats = self.apply(events, {"10": "9318", "20": None})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_differing_user_visible_payload_is_retained_and_reported(self) -> None:
        events = [event("10"), event("20", category="community")]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)
        self.assertEqual(stats["blocked_group_count"], 1)
        self.assertTrue(stats["qa_pass"])
        blocked = stats["blocked_groups"][0]
        self.assertEqual(blocked["classification"], "blocked_user_visible_payload_mismatch")
        self.assertEqual(blocked["differing_fields"][0]["field"], "event.category")

    def test_adult_youth_event_type_conflict_remains_separate(self) -> None:
        events = [
            event("10", event_type="Sport - Adult"),
            event("20", event_type="Sport - Youth"),
        ]
        kept, stats = self.apply(events, {"10": "9318", "20": "9318"})
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["suppressed_projection_count"], 0)
        self.assertEqual(stats["blocked_group_count"], 1)
        self.assertEqual(stats["blocked_record_count"], 2)
        self.assertEqual(stats["fatal_blocked_group_count"], 0)
        self.assertTrue(stats["qa_pass"])
        blocked = stats["blocked_groups"][0]
        self.assertEqual(blocked["classification"], "blocked_event_type_conflict")
        self.assertEqual(blocked["differing_fields"][0]["field"], "nycif.event_type")
        self.assertEqual(
            {item["value"] for item in blocked["differing_fields"][0]["values"]},
            {"Sport - Adult", "Sport - Youth"},
        )

    def test_existing_supplemental_behavior_unchanged(self) -> None:
        events = [
            {
                "id": "review_supplemental:calendar:1@2026-07-16",
                "title": "Access Benefits Fair",
                "location": "123 Main St",
                "latitude": None,
                "longitude": None,
                "source": {"dataset": "nyc-citywide-events-calendar-api", "source_event_id": "1"},
                "nycif": {
                    "event_date": "2026-07-16",
                    "coordinate_status": "list_only",
                    "manual_review_status": "pending",
                    "public_supplemental": True,
                },
            },
            {
                "id": "nyc-parks-bigapps-events:2@2026-07-16",
                "title": "Access Benefits Fair",
                "location": "123 Main St",
                "latitude": 40.75,
                "longitude": -73.98,
                "source": {"dataset": "nyc-parks-bigapps-events", "source_event_id": "2"},
                "nycif": {"event_date": "2026-07-16", "coordinate_status": "map_ready", "manual_review_status": "approved"},
            },
        ]
        kept, stats = dedupe_approved_events(events)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], "nyc-parks-bigapps-events:2@2026-07-16")
        self.assertEqual(stats["removed_duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
