#!/usr/bin/env python3
"""Extend the guarded V3+P11 transaction with durable location reuse.

The reuse lane runs after approximate recovery and before street-route geometry.
This ordering lets prior durable exact knowledge safely upgrade a current
non-exact occurrence while preserving the dedicated route lane and all P11 gates.
The final approximate-reader gate validates canonical final state rather than
requiring it to equal the pre-reuse recovery-stage count.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from scripts.prepare_p11_route_runtime_validator import transform as transform_p11
except ModuleNotFoundError:  # pragma: no cover
    from prepare_p11_route_runtime_validator import transform as transform_p11  # type: ignore[no-redef]

COMPILE_ANCHOR = '''    scripts/build_approximate_marker_reader_v1.py \\
    scripts/build_street_segment_route_authority_v1.py \\
    scripts/augment_daily_data_health_v03.py
'''
COMPILE_WITH_REUSE = '''    scripts/build_approximate_marker_reader_v1.py \\
    scripts/apply_durable_location_reuse_v1.py \\
    scripts/build_street_segment_route_authority_v1.py \\
    scripts/augment_daily_data_health_v03.py
'''

STAGE_ANCHOR = '''  run_stage \\
    "approximate_marker_recovery" \\
    "apply_approximate_marker_recovery_v1" \\
    python scripts/apply_approximate_marker_recovery_v1.py
  run_stage \\
    "street_segment_route_geometry" \\
'''
STAGE_WITH_REUSE = '''  run_stage \\
    "approximate_marker_recovery" \\
    "apply_approximate_marker_recovery_v1" \\
    python scripts/apply_approximate_marker_recovery_v1.py
  run_stage \\
    "durable_location_reuse" \\
    "apply_durable_location_reuse_v1" \\
    python scripts/apply_durable_location_reuse_v1.py
  run_stage \\
    "street_segment_route_geometry" \\
'''

STATUS_ANCHOR = '''approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))
route_safe = json.load(open("data/reader-safe/street-segment-routes-v1-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''
STATUS_WITH_REUSE = '''approx_safe = json.load(open("data/reader-safe/approximate-marker-recovery-v1-status.json"))
reuse_safe = json.load(open("data/durable_location_reuse_v1_report.json"))
route_safe = json.load(open("data/reader-safe/street-segment-routes-v1-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
'''

LEGACY_APPROX_COUNT_QA = '''if approx_safe.get("approximate_marker_count") != approx_recovery.get("recovered_approximate_markers"):
    sys.exit(
        "approximate recovery/reader counts disagree: "
        f"recovery={approx_recovery.get('recovered_approximate_markers')}, "
        f"reader={approx_safe.get('approximate_marker_count')}"
    )
'''
FINAL_APPROX_COUNT_QA = '''if approx_safe.get("counts_match_final_contract") is not True:
    sys.exit(
        "final approximate reader/canonical contract counts disagree: "
        f"final_contract={approx_safe.get('final_contract_count')}, "
        f"reader={approx_safe.get('approximate_marker_count')}"
    )
if approx_safe.get("recovery_count_is_diagnostic_only") is not True:
    sys.exit("approximate reader did not mark recovery-stage count as diagnostic")
'''

QA_ANCHOR = '''if not route_safe.get("qa_pass"):
    sys.exit("street route reader authority audit failed")
'''
QA_WITH_REUSE = '''if not reuse_safe.get("qa_pass"):
    sys.exit("durable location reuse audit failed")
if reuse_safe.get("invalid_reuse_count") != 0:
    sys.exit("durable location reuse emitted invalid geography")
if reuse_safe.get("ambiguous_promotions") != 0:
    sys.exit("durable location reuse promoted an ambiguous alias")
if reuse_safe.get("route_point_promotions") != 0:
    sys.exit("durable location reuse converted a route claim into a point")
if not route_safe.get("qa_pass"):
    sys.exit("street route reader authority audit failed")
'''

GIT_ADD_ANCHOR = '''    data/reader-safe/approximate-marker-recovery-v1-status.json \\
    data/reader-safe/street-segment-routes-v1.geojson \\
'''
GIT_ADD_WITH_REUSE = '''    data/reader-safe/approximate-marker-recovery-v1-status.json \\
    data/durable_location_reuse_v1_report.json \\
    data/reader-safe/street-segment-routes-v1.geojson \\
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}; found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    transformed = transform_p11(source)
    for old, new, label in (
        (COMPILE_ANCHOR, COMPILE_WITH_REUSE, "location reuse compile anchor"),
        (STAGE_ANCHOR, STAGE_WITH_REUSE, "location reuse stage anchor"),
        (STATUS_ANCHOR, STATUS_WITH_REUSE, "location reuse status anchor"),
        (LEGACY_APPROX_COUNT_QA, FINAL_APPROX_COUNT_QA, "final approximate count QA anchor"),
        (QA_ANCHOR, QA_WITH_REUSE, "location reuse QA anchor"),
        (GIT_ADD_ANCHOR, GIT_ADD_WITH_REUSE, "location reuse git add anchor"),
    ):
        transformed = replace_once(transformed, old, new, label)

    required = (
        "apply_durable_location_reuse_v1.py",
        '"durable_location_reuse"',
        "durable_location_reuse_v1_report.json",
        "durable location reuse promoted an ambiguous alias",
        "durable location reuse converted a route claim into a point",
        "counts_match_final_contract",
        "recovery_count_is_diagnostic_only",
    )
    for token in required:
        if token not in transformed:
            raise RuntimeError(f"required durable reuse transform missing: {token}")
    if "approximate recovery/reader counts disagree" in transformed:
        raise RuntimeError("legacy pre-reuse approximate count gate survived durable reuse transform")
    return transformed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    transformed = transform(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transformed, encoding="utf-8")
    print(f"prepared V3 + durable location reuse + P11 transaction: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
