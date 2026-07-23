#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_approved_dedupe import (  # noqa: E402
    SHARED_CEMS_PRIVATE_REPORT_PATH,
    SHARED_CEMS_PROHIBITED_PUBLIC_KEYS,
    SHARED_CEMS_PUBLIC_SUMMARY_PATH,
    build_cems_source_lookup,
    build_shared_cems_public_summary,
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
) -> dict[str, Any]:
    event_id = canonical_id or f"{dataset}:{source_event_id}@{day}"
    return {
        "id": event_id,
        "event_group_id": event_id,
        "parent_event_id": None,
        "title": "Soccer - Non Regulation",
        "category": category,
        "start_date_time": f"{day}T{start}-04:00",
        "end_date_time": f"{day}T{end}-04:00",
        "location": location,
        "latitude": latitude,
        "longitude": longitude,
        "source": {
            "dataset": dataset,
            "source_event_id": source_event_id,
        },
        "nycif": {
            "event_date": day,
            "event_type": event_type,
        },
    }


def lookups(
    events: list[dict[str, Any]],
    cems_by_id: dict[str, str | None],
):
    rows = [
        {
            "source_dataset": item["source"]["dataset"],
            "source_event_id": item["source"]["source_event_id"],
            "source_cemsid": cems_by_id.get(
                item["source"]["source_event_id"]
            ),
            "event_name": item["title"],
        }
        for item in events
    ]
    return build_cems_source_lookup(
        {"data/raw_nyc_open_data_snapshot.json": rows}
    )


def nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(nested_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(nested_keys(item))
    return keys


class SharedCemsOccurrenceDedupeTests(unittest.TestCase):
    def apply(
        self,
        events: list[dict[str, Any]],
        cems_by_id: dict[str, str | None],
    ):
        cems, evidence = lookups(events, cems_by_id)
        return dedupe_shared_cems_occurrences(
            events,
            cems,
            evidence,
        )

    def assert_no_suppression(
        self,
        events: list[dict[str, Any]],
        cems_by_id: dict[str, str | None],
    ) -> None:
        kept, stats = self.apply(events, cems_by_id)
        self.assertEqual(len(kept), len(events))
        self.assertEqual(stats["suppressed_projection_count"], 0)

    def test_group_sizes_and_representative(self) -> None:
        for size in (2, 3):
            with self.subTest(size=size):
                ids = [str(value) for value in range(size * 10, 0, -10)]
                events = [event(source_id) for source_id in ids]
                kept, stats = self.apply(
                    events,
                    {source_id: "9318" for source_id in ids},
                )
                self.assertEqual(
                    kept[0]["source"]["source_event_id"],
                    "10",
                )
                self.assertEqual(stats["group_member_count"], size)
                self.assertEqual(
                    stats["suppressed_projection_count"],
                    size - 1,
                )

    def test_reversed_input_order_is_deterministic(self) -> None:
        forward = [event("10"), event("20"), event("30")]
        reverse = list(reversed(copy.deepcopy(forward)))
        first, first_stats = self.apply(
            forward,
            {"10": "9318", "20": "9318", "30": "9318"},
        )
        second, second_stats = self.apply(
            reverse,
            {"10": "9318", "20": "9318", "30": "9318"},
        )
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(
            first_stats["groups"][0]["representative"]["canonical_id"],
            second_stats["groups"][0]["representative"]["canonical_id"],
        )

    def test_nonnumeric_ids_use_canonical_tiebreak(self) -> None:
        first = event(
            "beta",
            canonical_id="tvpp-9vvx:a@2026-07-22",
        )
        second = event(
            "alpha",
            canonical_id="tvpp-9vvx:z@2026-07-22",
        )
        kept, _ = self.apply(
            [first, second],
            {"alpha": "9318", "beta": "9318"},
        )
        self.assertEqual(
            kept[0]["source"]["source_event_id"],
            "beta",
        )

    def test_contract_differences_remain_separate(self) -> None:
        cases = {
            "date": (
                [event("10"), event("20", day="2026-07-23")],
                {"10": "9318", "20": "9318"},
            ),
            "start": (
                [event("10"), event("20", start="19:00:00")],
                {"10": "9318", "20": "9318"},
            ),
            "end": (
                [event("10"), event("20", end="21:00:00")],
                {"10": "9318", "20": "9318"},
            ),
            "location": (
                [
                    event("10"),
                    event("20", location="Chelsea Park Soccer 02"),
                ],
                {"10": "9318", "20": "9318"},
            ),
            "coordinates": (
                [event("10"), event("20", latitude=40.749942)],
                {"10": "9318", "20": "9318"},
            ),
            "cems": (
                [event("10"), event("20")],
                {"10": "9318", "20": "9319"},
            ),
            "dataset": (
                [
                    event("10"),
                    event("20", dataset="other-dataset"),
                ],
                {"10": "9318", "20": "9318"},
            ),
            "missing-cems": (
                [event("10"), event("20")],
                {"10": "9318", "20": None},
            ),
        }
        for name, (events, cems_by_id) in cases.items():
            with self.subTest(name=name):
                self.assert_no_suppression(events, cems_by_id)

    def test_differing_visible_payload_is_blocked(self) -> None:
        events = [
            event("10"),
            event("20", category="community"),
        ]
        kept, stats = self.apply(
            events,
            {"10": "9318", "20": "9318"},
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["blocked_group_count"], 1)
        self.assertTrue(stats["qa_pass"])
        blocked = stats["blocked_groups"][0]
        self.assertEqual(
            blocked["classification"],
            "blocked_user_visible_payload_mismatch",
        )
        self.assertEqual(
            blocked["differing_fields"][0]["field"],
            "event.category",
        )

    def test_adult_youth_conflict_is_classified(self) -> None:
        events = [
            event("10", event_type="Sport - Adult"),
            event("20", event_type="Sport - Youth"),
        ]
        kept, stats = self.apply(
            events,
            {"10": "9318", "20": "9318"},
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["blocked_record_count"], 2)
        self.assertEqual(stats["fatal_blocked_group_count"], 0)
        blocked = stats["blocked_groups"][0]
        self.assertEqual(
            blocked["classification"],
            "blocked_event_type_conflict",
        )

    def test_external_parent_reference_fails_closed(self) -> None:
        first = event("10")
        second = event("20")
        child = event(
            "30",
            canonical_id="tvpp-9vvx:child@2026-07-22",
            location="Different Field",
        )
        child["parent_event_id"] = second["id"]
        events = [first, second, child]

        kept, stats = self.apply(
            events,
            {"10": "9318", "20": "9318", "30": None},
        )

        self.assertEqual(len(kept), 3)
        self.assertFalse(stats["qa_pass"])
        self.assertEqual(stats["fatal_blocked_group_count"], 1)
        blocked = stats["blocked_groups"][0]
        self.assertIn(
            "externally_referenced_candidate_member",
            blocked["reasons"],
        )
        self.assertEqual(
            blocked["external_references"][0]["field"],
            "parent_event_id",
        )

    def test_public_summary_boundary_is_explicit(self) -> None:
        stats = {
            "contract_version": "shared-cems-occurrence-v1",
            "target_dataset": "tvpp-9vvx",
            "input_count": 31213,
            "output_count": 30944,
            "group_count": 256,
            "group_member_count": 525,
            "representative_count": 256,
            "suppressed_projection_count": 269,
            "blocked_group_count": 11,
            "blocked_record_count": 22,
            "fatal_blocked_group_count": 0,
            "qa_pass": True,
            "groups": [{"source_cemsid": "private"}],
        }
        summary = build_shared_cems_public_summary(
            stats,
            "2026-07-23T00:00:00Z",
        )

        self.assertTrue(
            SHARED_CEMS_PRIVATE_REPORT_PATH.startswith("data/reports/")
        )
        self.assertTrue(
            SHARED_CEMS_PUBLIC_SUMMARY_PATH.startswith(
                "data/schema-v1-discovery/"
            )
        )
        self.assertTrue(
            nested_keys(summary).isdisjoint(
                SHARED_CEMS_PROHIBITED_PUBLIC_KEYS
            )
        )
        self.assertNotIn("groups", summary)
        self.assertNotIn("blocked_groups", summary)

    def test_existing_supplemental_behavior_unchanged(self) -> None:
        supplemental = {
            "id": "review_supplemental:calendar:1@2026-07-16",
            "title": "Access Benefits Fair",
            "location": "123 Main St",
            "latitude": None,
            "longitude": None,
            "source": {
                "dataset": "nyc-citywide-events-calendar-api",
                "source_event_id": "1",
            },
            "nycif": {
                "event_date": "2026-07-16",
                "coordinate_status": "list_only",
                "manual_review_status": "pending",
                "public_supplemental": True,
            },
        }
        official = {
            "id": "nyc-parks-bigapps-events:2@2026-07-16",
            "title": "Access Benefits Fair",
            "location": "123 Main St",
            "latitude": 40.75,
            "longitude": -73.98,
            "source": {
                "dataset": "nyc-parks-bigapps-events",
                "source_event_id": "2",
            },
            "nycif": {
                "event_date": "2026-07-16",
                "coordinate_status": "map_ready",
                "manual_review_status": "approved",
            },
        }

        kept, stats = dedupe_approved_events(
            [supplemental, official]
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], official["id"])
        self.assertEqual(stats["removed_duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
