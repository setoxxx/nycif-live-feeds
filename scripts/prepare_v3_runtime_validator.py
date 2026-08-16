#!/usr/bin/env python3
"""Prepare the production refresh transaction with current V3 runtime gates.

The production transaction predates the fail-closed V3 semantic projector and
contains two legacy final-runtime assumptions:

1. the legacy staged MAP_READY feed owns public availability; and
2. cross-date street suppression is reported by the staged manifest.

The canonical V3 health and MapLibre reader-safe artifacts now own public
availability. Both must report the same positive certified marker count. The
legacy staged feed remains internally validated telemetry, while the current
cross-date safety count is emitted by the READY daily-health pipeline.

This helper performs two fail-closed, exact-source transformations into a
temporary execution copy. It never changes the repository transaction script.
If either expected legacy block is missing, duplicated, or has drifted,
preparation fails.
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
# reader-safe MapLibre status jointly own public marker availability.
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
# Current V3 daily health owns this runtime safety aggregate. Missing, boolean,
# negative, or non-integer values are not evidence; any non-zero count fails.
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


def _replace_exactly_once(source: str, legacy: str, replacement: str, label: str) -> str:
    occurrences = source.count(legacy)
    if occurrences != 1:
        raise RuntimeError(f"expected exactly one {label}; found {occurrences}")
    transformed = source.replace(legacy, replacement, 1)
    if legacy in transformed:
        raise RuntimeError(f"{label} remained after transform")
    return transformed


def transform(source: str) -> str:
    transformed = _replace_exactly_once(
        source,
        LEGACY_BLOCK,
        V3_BLOCK,
        "legacy staged MAP_READY validation block",
    )
    transformed = _replace_exactly_once(
        transformed,
        LEGACY_CROSS_DATE_BLOCK,
        V3_CROSS_DATE_BLOCK,
        "legacy cross-date suppression validation block",
    )
    if "jointly own public marker availability" not in transformed:
        raise RuntimeError("V3 canonical availability validation block was not installed")
    if 'health_pipeline.get(' not in transformed:
        raise RuntimeError("V3 cross-date suppression validation block was not installed")
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
    print(f"prepared V3 runtime transaction: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
