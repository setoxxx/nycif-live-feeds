#!/usr/bin/env python3
"""Prepare the production refresh transaction with current V3 runtime gates.

The repository transaction predates parts of the fail-closed V3 runtime. This
helper performs exact-source transformations into a temporary execution copy so
current production gates and recovery stages run atomically without mutating the
source transaction script itself.

Approximate-marker recovery is a separate authority class. It may restore useful
point placement only when current source location evidence agrees with a prior
stored point. It never grants MAP_READY/certified_pin, and street-route claims
remain excluded from point recovery.
"""
from __future__ import annotations

import argparse
from pathlib import Path

LEGACY_BLOCK = '''if not isinstance(staged_events, list) or not staged_events:
    sys.exit("staged map-ready feed has no events")
if staged_manifest.get("staged_feed_events") != len(staged_events):
    sys.exit("staged manifest count does not match staged rows")
'''

V3_BLOCK = '''if not isinstance(staged_events, list):
    sys.exit("staged map-ready feed is not a list")
if staged_manifest.get("staged_feed_events") != len(staged_events):
    sys.exit("staged manifest count does not match staged rows")

# The legacy staged feed is telemetry only. Canonical V3 health and the
# reader-safe MapLibre status jointly own public exact-marker availability.
health_v3_runtime = health.get("v3_runtime") if isinstance(health.get("v3_runtime"), dict) else {}
v3_runtime_map_ready = health_v3_runtime.get("map_ready_count")
maplibre_exact_markers = map_safe.get("exact_marker_count")

for label, value in (
    ("health.v3_runtime.map_ready_count", v3_runtime_map_ready),
    ("map_safe.exact_marker_count", maplibre_exact_markers),
):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        sys.exit(f"{label} must be a positive integer: {value!r}")

if maplibre_exact_markers != v3_runtime_map_ready:
    sys.exit(
        "canonical V3 and MapLibre marker counts disagree: "
        f"v3_runtime_map_ready={v3_runtime_map_ready}, "
        f"maplibre_exact_markers={maplibre_exact_markers}"
    )
'''

LEGACY_CROSS_DATE_BLOCK = '''if staged_manifest.get("cross_date_street_occurrences_suppressed") != 0:
    sys.exit("cross-date recurring street occurrences were suppressed")
'''

V3_CROSS_DATE_BLOCK = '''health_pipeline = health.get("pipeline") if isinstance(health.get("pipeline"), dict) else {}
cross_date_street_occurrences_suppressed = health_pipeline.get(
    "cross_date_street_occurrences_suppressed"
)
if (
    isinstance(cross_date_street_occurrences_suppressed, bool)
    or not isinstance(cross_date_street_occurrences_suppressed, int)
    or cross_date_street_occurrences_suppressed != 0
):
    sys.exit(
        "cross-date recurring street occurrence gate failed: "
        f"{cross_date_street_occurrences_suppressed!r}"
    )
'''

COMPILE_BLOCK = '''    scripts/build_maplibre_reader_safe_v03.py \\
    scripts/augment_daily_data_health_v03.py
'''
COMPILE_WITH_RECOVERY_BLOCK = '''    scripts/build_maplibre_reader_safe_v03.py \\
    scripts/apply_approximate_marker_recovery_v1.py \\
    scripts/build_maplibre_reader_safe_with_approx_v1.py \\
    scripts/build_approximate_marker_reader_v1.py \\
    scripts/augment_daily_data_health_v03.py
'''

PROJECTOR_BLOCK = '''  run_stage \\
    "full_discovery_projection_and_dedupe" \\
    "project_events_discovery_v03" \\
    python scripts/project_events_discovery_v03.py
  run_stage \\
    "strict_source_reconciliation" \\
'''
PROJECTOR_WITH_RECOVERY_BLOCK = '''  run_stage \\
    "full_discovery_projection_and_dedupe" \\
    "project_events_discovery_v03" \\
    python scripts/project_events_discovery_v03.py
  run_stage \\
    "approximate_marker_recovery" \\
    "apply_approximate_marker_recovery_v1" \\
    python scripts/apply_approximate_marker_recovery_v1.py
  run_stage \\
    "strict_source_reconciliation" \\
'''

MAP_READER_BLOCK = '''  run_stage \\
    "maplibre_reader_safe_projection" \\
    "build_maplibre_reader_safe_v03" \\
    python scripts/build_maplibre_reader_safe_v03.py
'''
MAP_READER_WITH_RECOVERY_BLOCK = '''  run_stage \\
    "maplibre_reader_safe_projection" \\
    "build_maplibre_reader_safe_with_approx_v1" \\
    python scripts/build_maplibre_reader_safe_with_approx_v1.py
  run_stage \\
    "maplibre_approximate_marker_overlay" \\
    "build_approximate_marker_reader_v1" \\
    python scripts/build_approximate_marker_reader_v1.py
'''

MAP_SAFE_LOAD_BLOCK = '''map_safe = json.load(open("data/reader-safe/national-map-events-v03-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''
MAP_SAFE_LOAD_WITH_RECOVERY_BLOCK = '''map_safe = json.load(open("data/reader-safe/national-map-events-v03-status.json"))
approx_recovery = json.load(open("data/approximate_marker_recovery_v1_report.json"))
approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''

MAP_SAFE_QA_BLOCK = '''if not map_safe.get("qa_pass"):
    sys.exit("MapLibre reader-safe marker audit failed")
'''
MAP_SAFE_QA_WITH_RECOVERY_BLOCK = '''if not map_safe.get("qa_pass"):
    sys.exit("MapLibre reader-safe marker audit failed")
if not approx_recovery.get("qa_pass"):
    sys.exit("approximate marker recovery audit failed")
if not approx_safe.get("qa_pass"):
    sys.exit("approximate marker reader overlay audit failed")
if approx_safe.get("exact_pin_count") != 0:
    sys.exit("approximate overlay attempted to grant exact-pin authority")
if approx_safe.get("approximate_marker_count") != approx_recovery.get("recovered_approximate_markers"):
    sys.exit(
        "approximate recovery/reader counts disagree: "
        f"recovery={approx_recovery.get('recovered_approximate_markers')}, "
        f"reader={approx_safe.get('approximate_marker_count')}"
    )
'''

GIT_ADD_BLOCK = '''    data/reader-safe/national-map-events-v03.geojson \\
    data/reader-safe/national-map-events-v03-status.json \\
'''
GIT_ADD_WITH_RECOVERY_BLOCK = '''    data/reader-safe/national-map-events-v03.geojson \\
    data/reader-safe/national-map-events-v03-status.json \\
    data/approximate_marker_recovery_v1_report.json \\
    data/reader-safe/approximate-marker-recovery-v1.geojson \\
    data/reader-safe/approximate-marker-recovery-v1-status.json \\
'''


def _replace_exactly_once(source: str, legacy: str, replacement: str, label: str) -> str:
    occurrences = source.count(legacy)
    if occurrences != 1:
        raise RuntimeError(f"expected exactly one {label}; found {occurrences}")
    transformed = source.replace(legacy, replacement, 1)
    if legacy in transformed:
        raise RuntimeError(f"{label} remained after transform")
    return transformed


def transform(source: str) -> str:
    replacements = (
        (LEGACY_BLOCK, V3_BLOCK, "legacy staged MAP_READY validation block"),
        (LEGACY_CROSS_DATE_BLOCK, V3_CROSS_DATE_BLOCK, "legacy cross-date suppression validation block"),
        (COMPILE_BLOCK, COMPILE_WITH_RECOVERY_BLOCK, "V3 compile list"),
        (PROJECTOR_BLOCK, PROJECTOR_WITH_RECOVERY_BLOCK, "Projector V3 stage boundary"),
        (MAP_READER_BLOCK, MAP_READER_WITH_RECOVERY_BLOCK, "MapLibre reader stage"),
        (MAP_SAFE_LOAD_BLOCK, MAP_SAFE_LOAD_WITH_RECOVERY_BLOCK, "MapLibre status load"),
        (MAP_SAFE_QA_BLOCK, MAP_SAFE_QA_WITH_RECOVERY_BLOCK, "MapLibre final QA block"),
        (GIT_ADD_BLOCK, GIT_ADD_WITH_RECOVERY_BLOCK, "reader-safe git add block"),
    )
    transformed = source
    for legacy, replacement, label in replacements:
        transformed = _replace_exactly_once(transformed, legacy, replacement, label)
    required = (
        "jointly own public exact-marker availability",
        "cross-date recurring street occurrence gate failed",
        "apply_approximate_marker_recovery_v1.py",
        "build_approximate_marker_reader_v1.py",
        "approximate overlay attempted to grant exact-pin authority",
        "approximate-marker-recovery-v1.geojson",
    )
    for token in required:
        if token not in transformed:
            raise RuntimeError(f"required V3 recovery transform missing: {token}")
    return transformed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    transformed = transform(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transformed, encoding="utf-8")
    print(f"prepared V3 runtime transaction with approximate recovery: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
