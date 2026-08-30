from __future__ import annotations

import unittest

from scripts.prepare_v3_runtime_validator import (
    COMPILE_BLOCK,
    GIT_ADD_BLOCK,
    LEGACY_BLOCK,
    LEGACY_CROSS_DATE_BLOCK,
    MAP_READER_BLOCK,
    MAP_SAFE_LOAD_BLOCK,
    MAP_SAFE_QA_BLOCK,
    PROJECTOR_BLOCK,
    V3_BLOCK,
    V3_CROSS_DATE_BLOCK,
    transform,
)


def source_fixture() -> str:
    return (
        "before\n"
        + COMPILE_BLOCK
        + PROJECTOR_BLOCK
        + MAP_READER_BLOCK
        + "import json\n"
        + MAP_SAFE_LOAD_BLOCK
        + LEGACY_BLOCK
        + LEGACY_CROSS_DATE_BLOCK
        + MAP_SAFE_QA_BLOCK
        + GIT_ADD_BLOCK
        + "after\n"
    )


class PrepareV3RuntimeValidatorTests(unittest.TestCase):
    def test_replaces_legacy_runtime_assertions(self) -> None:
        transformed = transform(source_fixture())
        self.assertNotIn(LEGACY_BLOCK, transformed)
        self.assertNotIn(LEGACY_CROSS_DATE_BLOCK, transformed)
        self.assertIn(V3_BLOCK, transformed)
        self.assertIn(V3_CROSS_DATE_BLOCK, transformed)
        self.assertIn("jointly own public exact-marker availability", transformed)
        self.assertIn("cross_date_street_occurrences_suppressed", transformed)

    def test_wires_approximate_recovery_into_atomic_transaction(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn("apply_approximate_marker_recovery_v1.py", transformed)
        self.assertIn("build_maplibre_reader_safe_with_approx_v1.py", transformed)
        self.assertIn("build_approximate_marker_reader_v1.py", transformed)
        self.assertLess(
            transformed.index("project_events_discovery_v03.py"),
            transformed.index("apply_approximate_marker_recovery_v1.py"),
        )
        self.assertLess(
            transformed.index("apply_approximate_marker_recovery_v1.py"),
            transformed.index("enforce_strict_discovery_reconciliation.py"),
        )

    def test_approximate_overlay_is_fail_closed_and_committed(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('approx_recovery = json.load(open("data/approximate_marker_recovery_v1_report.json"))', transformed)
        self.assertIn('approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))', transformed)
        self.assertIn("approximate overlay attempted to grant exact-pin authority", transformed)
        self.assertIn("approximate recovery/reader counts disagree", transformed)
        self.assertIn("data/approximate_marker_recovery_v1_report.json", transformed)
        self.assertIn("data/reader-safe/approximate-marker-recovery-v1.geojson", transformed)
        self.assertIn("data/reader-safe/approximate-marker-recovery-v1-status.json", transformed)

    def test_refuses_missing_map_ready_legacy_block(self) -> None:
        fixture = source_fixture().replace(LEGACY_BLOCK, "")
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 0"):
            transform(fixture)

    def test_refuses_duplicate_map_ready_legacy_blocks(self) -> None:
        fixture = source_fixture().replace(LEGACY_BLOCK, LEGACY_BLOCK + LEGACY_BLOCK)
        with self.assertRaisesRegex(RuntimeError, "legacy staged MAP_READY.*found 2"):
            transform(fixture)

    def test_refuses_missing_cross_date_legacy_block(self) -> None:
        fixture = source_fixture().replace(LEGACY_CROSS_DATE_BLOCK, "")
        with self.assertRaisesRegex(RuntimeError, "legacy cross-date suppression.*found 0"):
            transform(fixture)

    def test_legacy_staged_feed_is_not_v3_availability_authority(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('staged_manifest.get("staged_feed_events")', transformed)
        self.assertIn('health_v3_runtime.get("map_ready_count")', transformed)
        self.assertIn('map_safe.get("exact_marker_count")', transformed)
        self.assertNotIn('v3.get("map_ready_count")', transformed)

    def test_canonical_v3_and_maplibre_exact_counts_are_positive_and_equal(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('("health.v3_runtime.map_ready_count", v3_runtime_map_ready)', transformed)
        self.assertIn('("map_safe.exact_marker_count", maplibre_exact_markers)', transformed)
        self.assertIn("maplibre_exact_markers != v3_runtime_map_ready", transformed)
        self.assertIn("canonical V3 and MapLibre marker counts disagree", transformed)

    def test_cross_date_gate_reads_ready_health_pipeline_not_staged_manifest(self) -> None:
        transformed = transform(source_fixture())
        self.assertIn('health.get("pipeline")', transformed)
        self.assertNotIn(
            'staged_manifest.get("cross_date_street_occurrences_suppressed")',
            transformed,
        )


if __name__ == "__main__":
    unittest.main()
