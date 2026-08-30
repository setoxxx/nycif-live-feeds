import unittest

from scripts.prepare_location_reuse_runtime_validator import transform


class LocationReuseRuntimeValidatorTests(unittest.TestCase):
    def test_transform_injects_reuse_between_approximate_and_route(self):
        source = '''#!/usr/bin/env bash
set -euo pipefail
python -m py_compile \\
    scripts/build_maplibre_reader_safe_v03.py \\
    scripts/augment_daily_data_health_v03.py
  run_stage \\
    "full_discovery_projection_and_dedupe" \\
    "project_events_discovery_v03" \\
    python scripts/project_events_discovery_v03.py
  run_stage \\
    "strict_source_reconciliation" \\
    "enforce_strict_discovery_reconciliation" \\
    python scripts/enforce_strict_discovery_reconciliation.py
  run_stage \\
    "maplibre_reader_safe_projection" \\
    "build_maplibre_reader_safe_v03" \\
    python scripts/build_maplibre_reader_safe_v03.py
map_safe = json.load(open("data/reader-safe/national-map-events-v03-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
if not isinstance(staged_events, list) or not staged_events:
    sys.exit("staged map-ready feed has no events")
if staged_manifest.get("staged_feed_events") != len(staged_events):
    sys.exit("staged manifest count does not match staged rows")
if staged_manifest.get("cross_date_street_occurrences_suppressed") != 0:
    sys.exit("cross-date recurring street occurrences were suppressed")
if not map_safe.get("qa_pass"):
    sys.exit("MapLibre reader-safe marker audit failed")
if not health.get("release_ready") or health.get("status") != "READY":
    sys.exit("daily data health is not READY")
    data/reader-safe/national-map-events-v03.geojson \\
    data/reader-safe/national-map-events-v03-status.json \\
'''
        transformed = transform(source)
        self.assertIn('"durable_location_reuse"', transformed)
        self.assertIn("apply_durable_location_reuse_v1.py", transformed)
        self.assertIn("durable_location_reuse_v1_report.json", transformed)
        self.assertLess(
            transformed.index('"approximate_marker_recovery"'),
            transformed.index('"durable_location_reuse"'),
        )
        self.assertLess(
            transformed.index('"durable_location_reuse"'),
            transformed.index('"street_segment_route_geometry"'),
        )

    def test_transform_replaces_pre_reuse_approximate_count_gate(self):
        source = '''#!/usr/bin/env bash
set -euo pipefail
python -m py_compile \\
    scripts/build_maplibre_reader_safe_v03.py \\
    scripts/augment_daily_data_health_v03.py
  run_stage \\
    "full_discovery_projection_and_dedupe" \\
    "project_events_discovery_v03" \\
    python scripts/project_events_discovery_v03.py
  run_stage \\
    "strict_source_reconciliation" \\
    "enforce_strict_discovery_reconciliation" \\
    python scripts/enforce_strict_discovery_reconciliation.py
  run_stage \\
    "maplibre_reader_safe_projection" \\
    "build_maplibre_reader_safe_v03" \\
    python scripts/build_maplibre_reader_safe_v03.py
map_safe = json.load(open("data/reader-safe/national-map-events-v03-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
if not isinstance(staged_events, list) or not staged_events:
    sys.exit("staged map-ready feed has no events")
if staged_manifest.get("staged_feed_events") != len(staged_events):
    sys.exit("staged manifest count does not match staged rows")
if staged_manifest.get("cross_date_street_occurrences_suppressed") != 0:
    sys.exit("cross-date recurring street occurrences were suppressed")
if not map_safe.get("qa_pass"):
    sys.exit("MapLibre reader-safe marker audit failed")
if not health.get("release_ready") or health.get("status") != "READY":
    sys.exit("daily data health is not READY")
    data/reader-safe/national-map-events-v03.geojson \\
    data/reader-safe/national-map-events-v03-status.json \\
'''
        transformed = transform(source)
        self.assertIn("counts_match_final_contract", transformed)
        self.assertIn("recovery_count_is_diagnostic_only", transformed)
        self.assertIn("final approximate reader/canonical contract counts disagree", transformed)
        self.assertNotIn("approximate recovery/reader counts disagree", transformed)


if __name__ == "__main__":
    unittest.main()
