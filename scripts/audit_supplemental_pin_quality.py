#!/usr/bin/env python3
"""Audit approved supplemental rows for pins outside named parent park polygons."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from coverage_gap_utils import parse_facility_in_parent, parse_intersection_in_parent
from geojson_polygon_utils import load_parks_properties_index, point_in_named_park

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data" / "supplemental_manual_approval_queue.json"
PARKS_REF_PATH = ROOT / "data" / "nyc_parks_properties_reference.json"
REPORT_PATH = ROOT / "data" / "supplemental_pin_quality_audit_report.json"


def main() -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    parks_index = load_parks_properties_index(PARKS_REF_PATH) if PARKS_REF_PATH.exists() else {}
    outside = []
    for row in queue.get("rows") or []:
        if (row.get("manual_review_status") or "") != "approved":
            continue
        lat, lng = row.get("proposed_lat"), row.get("proposed_lng")
        if lat is None or lng is None:
            continue
        display = row.get("display_location") or ""
        parent = None
        parsed = parse_facility_in_parent(display) or parse_intersection_in_parent(display)
        if parsed and len(parsed) == 2:
            parent = parsed[1]
        elif parsed and len(parsed) == 3:
            parent = parsed[2]
        if not parent or not parks_index:
            continue
        if not point_in_named_park(float(lat), float(lng), parent, parks_index):
            outside.append(
                {
                    "rank": row.get("rank"),
                    "display_location": display,
                    "parent_park": parent,
                    "proposed_lat": lat,
                    "proposed_lng": lng,
                    "geocoder_source": row.get("geocoder_source"),
                }
            )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parks_reference_loaded": bool(parks_index),
        "approved_outside_parent_polygon_count": len(outside),
        "rows": outside[:100],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Outside parent polygon: {len(outside)}")


if __name__ == "__main__":
    main()
