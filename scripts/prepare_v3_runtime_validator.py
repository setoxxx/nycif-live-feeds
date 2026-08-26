#!/usr/bin/env python3
"""Prepare the production refresh transaction with current V3 and Supabase gates.

The production transaction predates the fail-closed V3 semantic projector and
contains two legacy final-runtime assumptions:

1. the legacy staged MAP_READY feed owns public availability; and
2. cross-date street suppression is reported by the staged manifest.

The canonical V3 health and MapLibre reader-safe artifacts now own public
availability. Both must report the same positive certified marker count. The
legacy staged feed remains internally validated telemetry, while the current
cross-date safety count is emitted by the READY daily-health pipeline.

This helper also installs the canonical Supabase authority sync immediately
after strict source reconciliation. The sync enumerates every source dataset in
the post-Projector-V3 canonical corpus, while preserving the existing bounded,
dataset-scoped atomic writer and finalizer. Any database failure therefore fails
the same production transaction before READY can be committed.

All transformations are fail-closed and exact-source. The helper writes only a
temporary execution copy. If an expected block is missing, duplicated, or has
drifted, preparation fails.
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

STRICT_RECONCILIATION_BLOCK = '''  run_stage \\
    "strict_source_reconciliation" \\
    "enforce_strict_discovery_reconciliation" \\
    python scripts/enforce_strict_discovery_reconciliation.py
'''

SUPABASE_AUTHORITY_BLOCK = STRICT_RECONCILIATION_BLOCK + '''  run_stage \\
    "supabase_event_authority_sync" \\
    "sync_supabase_event_authority" \\
    python scripts/sync_supabase_event_authority_all.py \\
      --input data/events_discovery_accepted_canonical_v02.json \\
      --chunk-size 500 \\
      --write
'''


def _replace_exactly_once(source: str, legacy: str, replacement: str, label: str) -> str:
    occurrences = source.count(legacy)
    if occurrences != 1:
        raise RuntimeError(f"expected exactly one {label}; found {occurrences}")
    transformed = source.replace(legacy, replacement, 1)
    if legacy != replacement and source.count(legacy) == 1 and transformed.count(replacement) != 1:
        raise RuntimeError(f"{label} replacement was not installed exactly once")
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
    transformed = _replace_exactly_once(
        transformed,
        STRICT_RECONCILIATION_BLOCK,
        SUPABASE_AUTHORITY_BLOCK,
        "strict source reconciliation block",
    )
    if "jointly own public marker availability" not in transformed:
        raise RuntimeError("V3 canonical availability validation block was not installed")
    if 'health_pipeline.get(' not in transformed:
        raise RuntimeError("V3 cross-date suppression validation block was not installed")
    if transformed.count('"supabase_event_authority_sync"') != 1:
        raise RuntimeError("Supabase authority stage was not installed exactly once")
    if transformed.count("scripts/sync_supabase_event_authority_all.py") != 1:
        raise RuntimeError("all-datasets Supabase authority command was not installed exactly once")
    if "--dataset tvpp-9vvx" in transformed:
        raise RuntimeError("TVPP-only Supabase authority scope remains in production transaction")
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
    print(f"prepared V3 + Supabase runtime transaction: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
