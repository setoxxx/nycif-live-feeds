from __future__ import annotations

import unittest

from scripts.prepare_v3_runtime_validator import (
    LEGACY_BLOCK,
    LEGACY_CROSS_DATE_BLOCK,
    STRICT_RECONCILIATION_BLOCK,
    SUPABASE_AUTHORITY_BLOCK,
    V3_BLOCK,
    V3_CROSS_DATE_BLOCK,
    transform,
)


def source_fixture() -> str:
    return (
        "before\n"
        + STRICT_RECONCILIATION_BLOCK
        + LEGACY_BLOCK
        + LEGACY_CROSS_DATE_BLOCK
        + "after\n"
    )


class PrepareV3RuntimeValidatorTests(unittest.TestCase):
    def test_replaces_legacy_runtime_assertions_and_installs_supabase_gate(self) -> None:
        transformed = transform(source_fixture())
        self.assertNotIn(LEGACY_BLOCK, transformed)
        self.assertNotIn(LEGACY_CROSS_DATE_BLOCK, transformed)
        self.assertIn(V3_BLOCK, transformed)
        self.assertIn(V3_CROSS_DATE_BLOCK, transformed)
        self.assertIn(SUPABASE_AUTHORITY_BLOCK, transformed)
        self.assertIn("jointly own public marker availability", transformed)
        self.assertIn("cross_date_street_occurrences_suppressed", transformed)
        self.assertEqual(transformed.count('"supabase_event_authority_sync"'), 1)
        self.assertEqual(transformed.count("scripts/sync_supabase_event_authority.py"), 1)

    def test_supabase_gate_is_immediately_after_strict_reconciliation(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn(SUPABASE_AUTHORITY_BLOCK, transformed)
        self.assertIn("--input data/events_discovery_accepted_canonical_v02.json", transformed)
        self.assertIn("--dataset tvpp-9vvx", transformed)
        self.assertIn("--chunk-size 500", transformed)
        self.assertIn("--write", transformed)
        self.assertLess(
            transformed.index('"strict_source_reconciliation"'),
            transformed.index('"supabase_event_authority_sync"'),
        )

    def test_refuses_missing_map_ready_legacy_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 0"):
            transform(STRICT_RECONCILIATION_BLOCK + LEGACY_CROSS_DATE_BLOCK)

    def test_refuses_duplicate_map_ready_legacy_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 2"):
            transform(
                STRICT_RECONCILIATION_BLOCK
                + LEGACY_BLOCK
                + LEGACY_BLOCK
                + LEGACY_CROSS_DATE_BLOCK
            )

    def test_refuses_missing_cross_date_legacy_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy cross-date suppression.*found 0"):
            transform(STRICT_RECONCILIATION_BLOCK + LEGACY_BLOCK)

    def test_refuses_duplicate_cross_date_legacy_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy cross-date suppression.*found 2"):
            transform(
                STRICT_RECONCILIATION_BLOCK
                + LEGACY_BLOCK
                + LEGACY_CROSS_DATE_BLOCK
                + LEGACY_CROSS_DATE_BLOCK
            )

    def test_refuses_missing_strict_reconciliation_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "strict source reconciliation.*found 0"):
            transform(LEGACY_BLOCK + LEGACY_CROSS_DATE_BLOCK)

    def test_refuses_duplicate_strict_reconciliation_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "strict source reconciliation.*found 2"):
            transform(
                STRICT_RECONCILIATION_BLOCK
                + STRICT_RECONCILIATION_BLOCK
                + LEGACY_BLOCK
                + LEGACY_CROSS_DATE_BLOCK
            )

    def test_legacy_staged_feed_is_not_v3_availability_authority(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('staged_manifest.get("staged_feed_events")', transformed)
        self.assertIn('health_v3_runtime.get("map_ready_count")', transformed)
        self.assertIn('map_safe.get("exact_marker_count")', transformed)
        self.assertNotIn("empty staged feed contradicts certified MAP_READY authority", transformed)
        self.assertNotIn("non-empty staged feed contradicts zero certified MAP_READY authority", transformed)
        self.assertNotIn('test_manifest.get("certified_map_ready_events")', transformed)
        self.assertNotIn('staged_manifest.get("certified_map_ready_before_dedupe")', transformed)

    def test_canonical_v3_and_maplibre_counts_are_positive_and_equal(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('("health.v3_runtime.map_ready_count", v3_runtime_map_ready)', transformed)
        self.assertIn('("map_safe.exact_marker_count", maplibre_exact_markers)', transformed)
        self.assertIn("isinstance(value, bool)", transformed)
        self.assertIn("not isinstance(value, int)", transformed)
        self.assertIn("value <= 0", transformed)
        self.assertIn("must be a positive integer", transformed)
        self.assertIn("maplibre_exact_markers != v3_runtime_map_ready", transformed)
        self.assertIn("canonical V3 and MapLibre marker counts disagree", transformed)

    def test_zero_row_rule_does_not_read_count_from_raw_v3_authority_report(self) -> None:
        transformed = transform(source_fixture())
        self.assertNotIn('v3.get("map_ready_count")', transformed)
        self.assertNotIn('(v3.get("map_state_counts") or {}).get("MAP_READY")', transformed)

    def test_cross_date_gate_reads_ready_health_pipeline_not_staged_manifest(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('health.get("pipeline")', transformed)
        self.assertIn('"cross_date_street_occurrences_suppressed"', transformed)
        self.assertNotIn(
            'staged_manifest.get("cross_date_street_occurrences_suppressed")',
            transformed,
        )

    def test_cross_date_gate_is_fail_closed_for_missing_malformed_or_nonzero(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn("isinstance(cross_date_street_occurrences_suppressed, bool)", transformed)
        self.assertIn("not isinstance(cross_date_street_occurrences_suppressed, int)", transformed)
        self.assertIn("cross_date_street_occurrences_suppressed != 0", transformed)
        self.assertIn("cross-date recurring street occurrence gate failed", transformed)


if __name__ == "__main__":
    unittest.main()
