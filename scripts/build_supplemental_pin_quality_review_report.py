#!/usr/bin/env python3
"""Build categorized supplemental pin quality review report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        parse_intersection_in_parent,
    )
    from scripts.geojson_polygon_utils import find_park_property_row, point_in_polygon_geometry
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        parse_intersection_in_parent,
    )
    from geojson_polygon_utils import find_park_property_row, point_in_polygon_geometry

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data" / "supplemental_manual_approval_queue.json"
REPORT_PATH = ROOT / "data" / "supplemental_pin_quality_review_report.json"

MEDIUM_CONFIDENCE_SOURCES = {
    "nyc_geosearch_planninglabs",
    "nyc_geosearch_planninglabs_midpoint",
    "nyc_parks_properties_reference",
}


def parent_park_from_display(display: str) -> str | None:
    parsed = parse_facility_in_parent(display) or parse_intersection_in_parent(display)
    if not parsed:
        return None
    if len(parsed) == 2:
        return parsed[1]
    return parsed[2]


def classify_row(row: dict[str, Any], parks_index: dict[str, list[dict[str, Any]]]) -> str:
    display = str(row.get("display_location") or "")
    parent = parent_park_from_display(display)
    if not parent:
        return "no_parent_context"
    lat, lng = row.get("proposed_lat"), row.get("proposed_lng")
    if lat is None or lng is None:
        return "missing_coordinates"
    prop = find_park_property_row(parent, row.get("borough"), parks_index)
    if not prop:
        return "no_polygon_match"
    geometry = prop.get("geometry") or prop.get("multipolygon")
    if not isinstance(geometry, dict):
        return "no_polygon_geometry"
    if point_in_polygon_geometry(float(lng), float(lat), geometry):
        return "inside_parent_polygon"
    source = str(row.get("geocoder_source") or "")
    if "pin-quality correction" in str(row.get("confidence_reason") or "").lower():
        return "outside_after_pin_quality_correction"
    if source == "nyc_parks_bigapps_events_snapshot":
        return "outside_parks_feed_intake"
    if source == "nyc_geoclient_intersection":
        return "outside_after_geoclient"
    if source in MEDIUM_CONFIDENCE_SOURCES:
        return "outside_medium_confidence_source"
    return "outside_other"


def priority_score(row: dict[str, Any], category: str) -> int:
    score = 0
    if row.get("geocoder_confidence") == "medium":
        score += 3
    if category.startswith("outside"):
        score += 2
    if category == "no_polygon_match":
        score += 2
    source = str(row.get("geocoder_source") or "")
    if source in MEDIUM_CONFIDENCE_SOURCES or "geosearch" in source:
        score += 2
    if "pin-quality correction" in str(row.get("confidence_reason") or "").lower():
        score += 1
    return score


def main() -> None:
    queue = load_json_file(QUEUE_PATH, {})
    rows = queue.get("approval_queue") or []
    parks_index = load_parks_properties_name_index()
    approved = [row for row in rows if (row.get("manual_review_status") or "") == "approved"]
    categories: Counter[str] = Counter()
    review_rows: list[dict[str, Any]] = []

    for row in approved:
        category = classify_row(row, parks_index)
        categories[category] += 1
        if category not in {"inside_parent_polygon", "no_parent_context"}:
            review_rows.append(
                {
                    "review_rank": row.get("review_rank"),
                    "category": category,
                    "priority_score": priority_score(row, category),
                    "display_location": row.get("display_location"),
                    "parent_park": parent_park_from_display(str(row.get("display_location") or "")),
                    "borough": row.get("borough"),
                    "geocoder_source": row.get("geocoder_source"),
                    "geocoder_confidence": row.get("geocoder_confidence"),
                    "proposed_lat": row.get("proposed_lat"),
                    "proposed_lng": row.get("proposed_lng"),
                }
            )

    review_rows.sort(key=lambda item: (-int(item["priority_score"]), int(item.get("review_rank") or 0)))
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "m11_supplemental_pin_quality_review",
        "approved_count": len(approved),
        "category_counts": dict(categories),
        "outside_parent_polygon_count": sum(
            count for key, count in categories.items() if key.startswith("outside")
        ),
        "no_polygon_match_count": categories.get("no_polygon_match", 0),
        "human_review_priority_rows": review_rows[:50],
        "public_map_modified": False,
        "location_cache_modified": False,
        "promotion_allowed": False,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Outside parent polygon: {report['outside_parent_polygon_count']}")
    print(f"Categories: {report['category_counts']}")


if __name__ == "__main__":
    main()
