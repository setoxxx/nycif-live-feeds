from __future__ import annotations

import unittest

from scripts.prepare_v3_runtime_validator import LEGACY_BLOCK, V3_BLOCK, transform


class PrepareV3RuntimeValidatorTests(unittest.TestCase):
    def test_replaces_exactly_one_legacy_nonempty_assertion(self) -> None:
        source = "before\n" + LEGACY_BLOCK + "after\n"
        transformed = transform(source)
        self.assertNotIn(LEGACY_BLOCK, transformed)
        self.assertIn(V3_BLOCK, transformed)
        self.assertIn("zero_map_ready_evidence", transformed)

    def test_refuses_missing_legacy_block(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "found 0"):
            transform("no legacy validation here\n")

    def test_refuses_duplicate_legacy_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            transform(LEGACY_BLOCK + LEGACY_BLOCK)

    def test_zero_row_rule_requires_three_independent_zero_counts(self) -> None:
        transformed = transform(LEGACY_BLOCK)
        self.assertIn('staged_manifest.get("certified_map_ready_before_dedupe")', transformed)
        self.assertIn('test_manifest.get("certified_map_ready_events")', transformed)
        self.assertIn('v3.get("map_ready_count")', transformed)
        self.assertIn('if mismatches:', transformed)
        self.assertIn("empty staged feed contradicts certified MAP_READY authority", transformed)

    def test_nonempty_feed_cannot_contradict_zero_authority(self) -> None:
        transformed = transform(LEGACY_BLOCK)
        self.assertIn("elif staged_certified_before_dedupe == 0", transformed)
        self.assertIn("non-empty staged feed contradicts zero certified MAP_READY authority", transformed)


if __name__ == "__main__":
    unittest.main()
