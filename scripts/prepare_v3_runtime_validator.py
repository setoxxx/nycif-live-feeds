#!/usr/bin/env python3
"""Prepare the production refresh transaction with current V3 runtime gates.

The production transaction predates the fail-closed V3 semantic projector and
contains two legacy final-runtime assumptions:

1. the staged MAP_READY feed must be non-empty; and
2. cross-date street suppression is reported by the staged manifest.

V3 can legitimately certify zero MAP_READY occurrences when every accepted
occurrence remains LIST_ONLY/REVIEW_REQUIRED, and the current cross-date safety
count is emitted by the READY daily-health pipeline rather than the staged
manifest.

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

# A zero-row staged feed is valid only when every independent semantic source
# agrees that there are zero certified MAP_READY occurrences. Never invent a
# marker merely to satisfy a non-empty runtime invariant.
staged_certified_before_dedupe = staged_manifest.get("certified_map_ready_before_dedupe")
test_certified_map_ready = test_manifest.get("certified_map_ready_events")
health_v3_runtime = health.get("v3_runtime") if isinstance(health.get("v3_runtime"), dict) else {}
v3_runtime_map_ready = health_v3_runtime.get("map_ready_count")

# The third count is computed by augment_daily_data_health_v03.py directly from
# canonical semantic rows. Missing, boolean, negative, or otherwise malformed
# values are not evidence and must fail closed.
if (
    isinstance(v3_runtime_map_ready, bool)
    or not isinstance(v3_runtime_map_ready, int)
    or v3_runtime_map_ready < 0
):
    sys.exit(
        "daily V3 runtime MAP_READY count is missing or malformed: "
        f"{v3_runtime_map_ready!r}"
    )
if not staged_events:
    zero_map_ready_evidence = {
        "staged_manifest.certified_map_ready_before_dedupe": staged_certified_before_dedupe,
        "test_manifest.certified_map_ready_events": test_certified_map_ready,
        "health.v3_runtime.map_ready_count": v3_runtime_map_ready,
    }
    mismatches = {key: value for key, value in zero_map_ready_evidence.items() if value != 0}
    if mismatches:
        sys.exit(f"empty staged feed contradicts certified MAP_READY authority: {mismatches}")
elif (
    staged_certified_before_dedupe == 0
    or test_certified_map_ready == 0
    or v3_runtime_map_ready == 0
):
    sys.exit(
        "non-empty staged feed contradicts zero certified MAP_READY authority: "
        f"staged_before_dedupe={staged_certified_before_dedupe}, "
        f"test_certified={test_certified_map_ready}, "
        f"v3_runtime_map_ready={v3_runtime_map_ready}"
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
    if "Never invent a" not in transformed:
        raise RuntimeError("V3 zero-MAP_READY validation block was not installed")
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
