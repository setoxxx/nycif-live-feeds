#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage6_audit",
    ROOT / "scripts" / "audit_stage6_city_sources.py",
)
assert SPEC and SPEC.loader
stage6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage6)


class Stage6AuditTests(unittest.TestCase):
    def test_normalization_and_date_key(self) -> None:
        self.assertEqual(stage6.normalized("WEST 33 STREET & 8 AVE"), "west 33 street 8 ave")
        self.assertEqual(stage6.date_key("2026-08-01T10:30:00.000"), "2026-08-01")
        self.assertEqual(stage6.date_key("not-a-date"), "")

    def test_approved_indexes_preserve_occurrence_dimensions(self) -> None:
        rows = [
            {
                "id": "approved-1",
                "start_date_time": "2026-08-01T10:30:00-04:00",
                "borough": "Brooklyn",
                "location": "East 74 Street between Avenue U and Avenue T",
                "source": {"source_event_id": "923896"},
            }
        ]
        source_ids, semantic = stage6.approved_indexes(rows)
        self.assertIn("923896", source_ids)
        self.assertIn(
            ("2026-08-01", "brooklyn", "east 74 street between avenue u and avenue t"),
            semantic,
        )

    def test_infrastructure_sources_never_promote_as_events(self) -> None:
        disposition, reasons = stage6.classify(
            {"role": "infrastructure_corroboration"},
            metadata_age=0,
            missing_required=[],
            current_future_count=100,
            current_error=None,
            has_location=True,
            has_direct_geometry=True,
            overlap_source_ids=0,
            overlap_semantic=0,
        )
        self.assertEqual(disposition, "infrastructure_context_only_not_public_event_feed")
        self.assertTrue(reasons)

    def test_event_source_without_future_rows_is_blocked(self) -> None:
        disposition, reasons = stage6.classify(
            {"role": "event_candidate"},
            metadata_age=1,
            missing_required=[],
            current_future_count=0,
            current_error=None,
            has_location=True,
            has_direct_geometry=False,
            overlap_source_ids=0,
            overlap_semantic=0,
        )
        self.assertEqual(disposition, "blocked_no_current_future_rows")
        self.assertIn("no current or future rows", reasons)

    def test_stale_advisory_source_is_blocked(self) -> None:
        disposition, _ = stage6.classify(
            {"role": "advisory_candidate"},
            metadata_age=400,
            missing_required=[],
            current_future_count=None,
            current_error="no_primary_date_field",
            has_location=True,
            has_direct_geometry=False,
            overlap_source_ids=0,
            overlap_semantic=0,
        )
        self.assertEqual(disposition, "blocked_stale_or_non_current_advisory_source")


if __name__ == "__main__":
    unittest.main()
