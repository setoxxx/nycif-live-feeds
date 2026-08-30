#!/usr/bin/env python3
"""Extend the guarded V3 refresh transaction with P11 street-route geometry.

The existing V3 transformer remains the base authority for point/approximate
recovery. This transformer applies that known-good transform first, then injects
P11 route acquisition, validation and staging using exact post-transform anchors.
Source drift therefore fails closed instead of silently skipping route gates.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from scripts.prepare_v3_runtime_validator import transform as transform_v3
except ModuleNotFoundError:  # pragma: no cover
    from prepare_v3_runtime_validator import transform as transform_v3  # type: ignore[no-redef]

COMPILE_ANCHOR = '''    scripts/build_approximate_marker_reader_v1.py \\
    scripts/augment_daily_data_health_v03.py
'''
COMPILE_WITH_ROUTE = '''    scripts/build_approximate_marker_reader_v1.py \\
    scripts/build_street_segment_route_authority_v1.py \\
    scripts/augment_daily_data_health_v03.py
'''

RECOVERY_STAGE_ANCHOR = '''  run_stage \\
    "approximate_marker_recovery" \\
    "apply_approximate_marker_recovery_v1" \\
    python scripts/apply_approximate_marker_recovery_v1.py
  run_stage \\
    "strict_source_reconciliation" \\
'''
RECOVERY_WITH_ROUTE_STAGE = '''  run_stage \\
    "approximate_marker_recovery" \\
    "apply_approximate_marker_recovery_v1" \\
    python scripts/apply_approximate_marker_recovery_v1.py
  run_stage \\
    "street_segment_route_geometry" \\
    "build_street_segment_route_authority_v1" \\
    bash scripts/run_street_segment_route_runtime_v1.sh
  run_stage \\
    "strict_source_reconciliation" \\
'''

STATUS_LOAD_ANCHOR = '''approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''
STATUS_LOAD_WITH_ROUTE = '''approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))
route_safe = json.load(open("data/reader-safe/street-segment-routes-v1-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''

QA_ANCHOR = '''if approx_safe.get("approximate_marker_count") != approx_recovery.get("recovered_approximate_markers"):
    sys.exit(
        "approximate recovery/reader counts disagree: "
        f"recovery={approx_recovery.get('recovered_approximate_markers')}, "
        f"reader={approx_safe.get('approximate_marker_count')}"
    )
if not health.get("release_ready") or health.get("status") != "READY":
'''
QA_WITH_ROUTE = '''if approx_safe.get("approximate_marker_count") != approx_recovery.get("recovered_approximate_markers"):
    sys.exit(
        "approximate recovery/reader counts disagree: "
        f"recovery={approx_recovery.get('recovered_approximate_markers')}, "
        f"reader={approx_safe.get('approximate_marker_count')}"
    )
if not route_safe.get("qa_pass"):
    sys.exit("street route reader authority audit failed")
for key in (
    "point_geometry_count",
    "invalid_geometry_count",
    "duplicate_occurrence_count",
    "canonical_duplicate_occurrence_count",
    "midpoint_publication_count",
):
    if route_safe.get(key) != 0:
        sys.exit(f"street route zero gate failed: {key}={route_safe.get(key)}")
if route_safe.get("area_geometry_count") != 0:
    sys.exit("street route lane unexpectedly emitted area geometry")
if not health.get("release_ready") or health.get("status") != "READY":
'''

GIT_ADD_ANCHOR = '''    data/reader-safe/approximate-marker-recovery-v1.geojson \\
    data/reader-safe/approximate-marker-recovery-v1-status.json \\
'''
GIT_ADD_WITH_ROUTE = '''    data/reader-safe/approximate-marker-recovery-v1.geojson \\
    data/reader-safe/approximate-marker-recovery-v1-status.json \\
    data/reader-safe/street-segment-routes-v1.geojson \\
    data/reader-safe/street-segment-routes-v1-status.json \\
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}; found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    transformed = transform_v3(source)
    for old, new, label in (
        (COMPILE_ANCHOR, COMPILE_WITH_ROUTE, "P11 compile anchor"),
        (RECOVERY_STAGE_ANCHOR, RECOVERY_WITH_ROUTE_STAGE, "P11 stage anchor"),
        (STATUS_LOAD_ANCHOR, STATUS_LOAD_WITH_ROUTE, "P11 status load anchor"),
        (QA_ANCHOR, QA_WITH_ROUTE, "P11 final QA anchor"),
        (GIT_ADD_ANCHOR, GIT_ADD_WITH_ROUTE, "P11 git add anchor"),
    ):
        transformed = replace_once(transformed, old, new, label)

    required = (
        "build_street_segment_route_authority_v1.py",
        "run_street_segment_route_runtime_v1.sh",
        "street-segment-routes-v1.geojson",
        "street-segment-routes-v1-status.json",
        "street route zero gate failed",
        '"midpoint_publication_count"',
    )
    for token in required:
        if token not in transformed:
            raise RuntimeError(f"required P11 route transform missing: {token}")
    return transformed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    transformed = transform(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transformed, encoding="utf-8")
    print(f"prepared V3 + P11 route runtime transaction: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
