#!/usr/bin/env python3
"""Prepare the production refresh transaction with the V3 zero-MAP_READY gate.

The production transaction predates the fail-closed V3 semantic projector and
contains a legacy assertion that the staged MAP_READY feed must be non-empty.
V3 can legitimately certify zero MAP_READY occurrences when every accepted
occurrence remains LIST_ONLY/REVIEW_REQUIRED and all exact-location zero gates
pass.

This helper performs one fail-closed, exact-source transformation into a
temporary execution copy. It never changes the repository transaction script.
If the expected legacy block is missing or has drifted, preparation fails.
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
v3_map_ready = v3.get("map_ready_count")
if v3_map_ready is None:
    v3_map_ready = (v3.get("map_state_counts") or {}).get("MAP_READY")
if not staged_events:
    zero_map_ready_evidence = {
        "staged_manifest.certified_map_ready_before_dedupe": staged_certified_before_dedupe,
        "test_manifest.certified_map_ready_events": test_certified_map_ready,
        "v3.map_ready_count": v3_map_ready,
    }
    mismatches = {key: value for key, value in zero_map_ready_evidence.items() if value != 0}
    if mismatches:
        sys.exit(f"empty staged feed contradicts certified MAP_READY authority: {mismatches}")
elif staged_certified_before_dedupe == 0 or test_certified_map_ready == 0 or v3_map_ready == 0:
    sys.exit(
        "non-empty staged feed contradicts zero certified MAP_READY authority: "
        f"staged_before_dedupe={staged_certified_before_dedupe}, "
        f"test_certified={test_certified_map_ready}, v3_map_ready={v3_map_ready}"
    )
'''


def transform(source: str) -> str:
    occurrences = source.count(LEGACY_BLOCK)
    if occurrences != 1:
        raise RuntimeError(
            "expected exactly one legacy staged MAP_READY validation block; "
            f"found {occurrences}"
        )
    transformed = source.replace(LEGACY_BLOCK, V3_BLOCK, 1)
    if LEGACY_BLOCK in transformed:
        raise RuntimeError("legacy staged MAP_READY validation block remained after transform")
    if "Never invent a" not in transformed:
        raise RuntimeError("V3 zero-MAP_READY validation block was not installed")
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
