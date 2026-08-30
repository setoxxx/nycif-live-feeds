from __future__ import annotations

import unittest

from scripts.prepare_p11_route_runtime_validator import transform
from tests.test_prepare_v3_runtime_validator import source_fixture


class PrepareP11RouteRuntimeValidatorTests(unittest.TestCase):
    def test_wires_route_runtime_after_approximate_recovery(self):
        transformed = transform(source_fixture())
        self.assertIn("build_street_segment_route_authority_v1.py", transformed)
        self.assertIn("run_street_segment_route_runtime_v1.sh", transformed)
        self.assertLess(
            transformed.index('"approximate_marker_recovery"'),
            transformed.index('"street_segment_route_geometry"'),
        )
        self.assertLess(
            transformed.index('"street_segment_route_geometry"'),
            transformed.index('"strict_source_reconciliation"'),
        )

    def test_route_artifacts_are_loaded_validated_and_staged(self):
        transformed = transform(source_fixture())
        self.assertIn('route_safe = json.load(open("data/reader-safe/street-segment-routes-v1-status.json"))', transformed)
        self.assertIn("street route reader authority audit failed", transformed)
        self.assertIn("street route zero gate failed", transformed)
        self.assertIn("data/reader-safe/street-segment-routes-v1.geojson", transformed)
        self.assertIn("data/reader-safe/street-segment-routes-v1-status.json", transformed)

    def test_route_lane_forbids_midpoint_and_point_publication(self):
        transformed = transform(source_fixture())
        self.assertIn('"point_geometry_count"', transformed)
        self.assertIn('"midpoint_publication_count"', transformed)
        self.assertIn('route_safe.get("area_geometry_count") != 0', transformed)

    def test_source_drift_fails_closed(self):
        fixture = source_fixture().replace("scripts/build_maplibre_reader_safe_v03.py", "scripts/renamed_reader.py")
        with self.assertRaises(RuntimeError):
            transform(fixture)


if __name__ == "__main__":
    unittest.main()
