#!/usr/bin/env python3
"""Apply park polygon pin correction to approved supplemental child-in-parent rows.

Relocates pins that fall outside the named parent park polygon into the park
interior centroid (staging queue only). Does not modify location_cache.json or
set promotion_allowed=true.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        parse_intersection_in_parent,
        save_json_file,
        utc_now_iso,
    )
    from scripts.geojson_polygon_utils import (
        find_park_property_row,
        point_in_polygon_geometry,
        snap_to_park_interior,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        parse_intersection_in_parent,
        save_json_file,
        utc_now_iso,
    )
    from geojson_polygon_utils import (
        find_park_property_row,
        point_in_polygon_geometry,
        snap_to_park_interior,
    )

QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
REPORT_PATH = DATA_DIR / "supplemental_pin_polygon_correction_report.json"


def parent_park_from_display(display: str) -> str | None:
    parsed = parse_facility_in_parent(display) or parse_intersection_in_parent(display)
    if not parsed:
        return None
    if len(parsed) == 2:
        return parsed[1]
    return parsed[2]


def run(*, dry_run: bool = False) -> int:
    payload = load_json_file(QUEUE_PATH, {})
    queue = payload.get("approval_queue") or []
    parks_index = load_parks_properties_name_index()
    outcomes: list[dict[str, Any]] = []
    corrected = 0
    skipped_inside = 0
    skipped_no_parent = 0
    skipped_no_polygon = 0
    skipped_snap_failed = 0
    skipped_still_outside = 0

    updated_queue: list[dict[str, Any]] = []
    for row in queue:
        if (row.get("manual_review_status") or "") != "approved":
            updated_queue.append(row)
            continue
        lat, lng = row.get("proposed_lat"), row.get("proposed_lng")
        if lat is None or lng is None:
            updated_queue.append(row)
            continue
        display = str(row.get("display_location") or "")
        parent = parent_park_from_display(display)
        if not parent:
            skipped_no_parent += 1
            updated_queue.append(row)
            continue
        prop = find_park_property_row(parent, row.get("borough"), parks_index)
        if not prop:
            skipped_no_polygon += 1
            outcomes.append(
                {
                    "review_rank": row.get("review_rank"),
                    "outcome": "skipped_no_polygon_match",
                    "parent_park": parent,
                    "display_location": display,
                }
            )
            updated_queue.append(row)
            continue
        geometry = prop.get("geometry") or prop.get("multipolygon")
        if not isinstance(geometry, dict):
            skipped_no_polygon += 1
            updated_queue.append(row)
            continue
        lat_f, lng_f = float(lat), float(lng)
        if point_in_polygon_geometry(lng_f, lat_f, geometry):
            skipped_inside += 1
            updated_queue.append(row)
            continue
        snapped = snap_to_park_interior(lat_f, lng_f, parent, row.get("borough"), parks_index)
        if not snapped:
            skipped_snap_failed += 1
            outcomes.append(
                {
                    "review_rank": row.get("review_rank"),
                    "outcome": "skipped_snap_failed",
                    "parent_park": parent,
                }
            )
            updated_queue.append(row)
            continue
        new_lat, new_lng, label = snapped
        if not point_in_polygon_geometry(float(new_lng), float(new_lat), geometry):
            skipped_still_outside += 1
            outcomes.append(
                {
                    "review_rank": row.get("review_rank"),
                    "outcome": "skipped_centroid_still_outside",
                    "parent_park": parent,
                    "display_location": display,
                    "proposed_lat": new_lat,
                    "proposed_lng": new_lng,
                }
            )
            updated_queue.append(row)
            continue

        out = dict(row)
        out["proposed_lat"] = new_lat
        out["proposed_lng"] = new_lng
        if out.get("geocoder_confidence") == "high":
            out["geocoder_confidence"] = "medium"
        out["confidence_reason"] = (
            f"Pin-quality correction: relocated pin into '{label}' park interior "
            f"(parent context '{parent}') for manual review only."
        )
        out["public_map_modified"] = False
        out["location_cache_modified"] = False
        out["staged_feed_modified"] = False
        out["promotion_allowed"] = False
        corrected += 1
        outcomes.append(
            {
                "review_rank": row.get("review_rank"),
                "outcome": "corrected",
                "parent_park": parent,
                "display_location": display,
                "old_lat": lat_f,
                "old_lng": lng_f,
                "new_lat": new_lat,
                "new_lng": new_lng,
                "geocoder_source": row.get("geocoder_source"),
            }
        )
        updated_queue.append(out)

    report = {
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_pin_polygon_correction",
        "dry_run": dry_run,
        "corrected_count": corrected,
        "skipped_inside_polygon_count": skipped_inside,
        "skipped_no_parent_context_count": skipped_no_parent,
        "skipped_no_polygon_match_count": skipped_no_polygon,
        "skipped_snap_failed_count": skipped_snap_failed,
        "skipped_centroid_still_outside_count": skipped_still_outside,
        "outcome_counts": dict(Counter(item["outcome"] for item in outcomes)),
        "public_map_modified": False,
        "location_cache_modified": False,
        "promotion_allowed": False,
        "outcomes": outcomes[:200],
    }
    save_json_file(REPORT_PATH, report)
    if not dry_run and corrected:
        save_json_file(QUEUE_PATH, {"generated_at_utc": report["generated_at_utc"], "approval_queue": updated_queue})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental park polygon pin corrections.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
