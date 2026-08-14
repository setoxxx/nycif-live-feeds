from __future__ import annotations

import unittest

from scripts.prepare_v3_runtime_validator import (
    LEGACY_BLOCK,
    LEGACY_CROSS_DATE_BLOCK,
    V3_BLOCK,
    V3_CROSS_DATE_BLOCK,
    transform,
)


def source_fixture() -> str:
    return "before\n" + LEGACY_BLOCK + LEGACY_CROSS_DATE_BLOCK + "after\n"


class PrepareV3RuntimeValidatorTests(unittest.TestCase):
    def test_replaces_both_legacy_runtime_assertions(self) -> None:
        transformed = transform(source_fixture())
        self.assertNotIn(LEGACY_BLOCK, transformed)
        self.assertNotIn(LEGACY_CROSS_DATE_BLOCK, transformed)
        self.assertIn(V3_BLOCK, transformed)
        self.assertIn(V3_CROSS_DATE_BLOCK, transformed)
        self.assertIn("zero_map_ready_evidence", transformed)
        self.assertIn("cross_date_street_occurrences_suppressed", transformed)

    def test_refuses_missing_map_ready_legacy_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 0"):
            transform(LEGACY_CROSS_DATE_BLOCK)

    def test_refuses_duplicate_map_ready_legacy_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 2"):
            transform(LEGACY_BLOCK + LEGACY_BLOCK + LEGACY_CROSS_DATE_BLOCK)

    def test_refuses_missing_cross_date_legacy_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy cross-date suppression.*found 0"):
            transform(LEGACY_BLOCK)

    def test_refuses_duplicate_cross_date_legacy_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "legacy cross-date suppression.*found 2"):
            transform(LEGACY_BLOCK + LEGACY_CROSS_DATE_BLOCK + LEGACY_CROSS_DATE_BLOCK)

    def test_zero_row_rule_requires_three_independent_zero_counts(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('staged_manifest.get("certified_map_ready_before_dedupe")', transformed)
        self.assertIn('test_manifest.get("certified_map_ready_events")', transformed)
        self.assertIn('health.get("v3_runtime")', transformed)
        self.assertIn('health_v3_runtime.get("map_ready_count")', transformed)
        self.assertIn('"health.v3_runtime.map_ready_count"', transformed)
        self.assertIn('if mismatches:', transformed)
        self.assertIn("empty staged feed contradicts certified MAP_READY authority", transformed)

    def test_zero_row_rule_does_not_read_count_from_raw_v3_authority_report(self) -> None:
        transformed = transform(source_fixture())
        self.assertNotIn('v3.get("map_ready_count")', transformed)
        self.assertNotIn('(v3.get("map_state_counts") or {}).get("MAP_READY")', transformed)

    def test_v3_runtime_count_is_fail_closed_when_missing_or_malformed(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn("isinstance(v3_runtime_map_ready, bool)", transformed)
        self.assertIn("not isinstance(v3_runtime_map_ready, int)", transformed)
        self.assertIn("v3_runtime_map_ready < 0", transformed)
        self.assertIn("daily V3 runtime MAP_READY count is missing or malformed", transformed)

    def test_nonempty_feed_cannot_contradict_zero_authority(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn("staged_certified_before_dedupe == 0", transformed)
        self.assertIn("v3_runtime_map_ready == 0", transformed)
        self.assertIn("non-empty staged feed contradicts zero certified MAP_READY authority", transformed)

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
