#!/usr/bin/env python3
"""Resolve leftover native-feed Pending rows that have a real official place.

Borough-only TVPP leftovers and citywide/multi-site rows stay unpinned.
This script writes a report only. It does not edit location_cache.json or
publish to the public map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import official_event_contract as contract
from scripts.tvpp_pin_resolver import TvppPinResolver

REPORT_PATH = ROOT / "data" / "reports" / "pin_remaining_native_pending_report.json"


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    resolver = TvppPinResolver.load_default()
    pinned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    for row in rows:
        display = str(row.get("display_location") or "")
        borough = str(row.get("borough") or "") or None
        dataset = str(row.get("source_dataset") or "")
        if not contract.native_map_row_visible(display, borough, dataset or None):
            skipped.append({**row, "reason": "unpinnable_borough_citywide_or_multi_site"})
            continue
        pin = resolver.resolve(display, borough)
        if not pin.resolved:
            missed.append({**row, "reason": "official_resolver_miss"})
            continue
        pinned.append(
            {
                **row,
                "lat": pin.lat,
                "lng": pin.lng,
                "geocoder_source": pin.source,
                "reason_code": pin.reason_code,
                "confidence_reason": pin.confidence_reason,
                "location_evidence": pin.evidence(),
            }
        )
    if resolver.live_calls:
        resolver.save_cache()
    return {
        "artifact_type": "pin_remaining_native_pending_report",
        "input_rows": len(rows),
        "pinned": len(pinned),
        "skipped_unpinnable": len(skipped),
        "missed": len(missed),
        "location_cache_modified": False,
        "public_map_modified": False,
        "promotion_allowed": False,
        "pinned_rows": pinned,
        "skipped_rows": skipped,
        "miss_rows": missed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="JSON list of pending rows")
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
    report = resolve_rows(rows)
    _write(REPORT_PATH, report)
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("_rows")}, indent=2))
    return 0 if report["missed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
