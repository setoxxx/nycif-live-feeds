#!/usr/bin/env python3
"""Run current daily preflight regressions without mutable historical feed assertions.

The August 1 live-occurrence behavior remains covered with deterministic fixtures.
After August 1, the real repository check uses the immutable Event 923896
certification artifact instead of current approved pages, which legitimately age
past occurrences out of the serving feed.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.test_live_event_intake_refresh as regression  # noqa: E402


def main() -> int:
    tests = (
        regression.test_required_block_party_uses_certified_brooklyn_segment,
        regression.test_general_segment_uses_alternate_intersection_queries,
        regression.test_cross_borough_geosearch_results_are_rejected,
        regression.test_required_event_public_feed_gate,
        regression.test_required_event_aug1_missing_fails_live,
        regression.test_required_event_aug2_real_certificate_passes,
        regression.test_required_event_aug2_missing_and_malformed_fail,
        regression.test_required_event_aug2_top_level_contract_failures,
        regression.test_required_event_aug2_nested_health_failure,
        regression.test_required_event_aug2_page_and_list_checks_are_fail_closed,
        regression.test_required_event_aug2_cross_surface_consistency,
        regression.test_modified_python_files_compile,
        regression.test_required_event_signature_compatible,
        regression.test_refresh_workflow_contract,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("current live event intake refresh regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
