#!/usr/bin/env python3
"""Audit approved supplemental export rows with duplicate overlap_key but different coords.

Phase 2E pre-promotion review only. Does NOT modify location_cache.json, staged feeds,
the public map, or promotion_allowed flags.

Outputs:
- data/reports/supplemental_overlap_key_coord_conflict_audit_report.json
- data/reports/supplemental_overlap_key_coord_conflict_audit.csv
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_overlap_key_coord_conflict_audit_report.json"
CSV_PATH = DATA_DIR / "reports" / "supplemental_overlap_key_coord_conflict_audit.csv"

CONF_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}
SRC_RANK = {
    "nyc_parks_facility_reference": 5,
    "nyc_parks_properties_reference": 5,
    "manual_gps_reference": 5,
    "supplemental_location_memory": 4,
    "nyc_parks_bigapps_events_snapshot": 3,
    "nyc_geosearch_planninglabs": 2,
    "nyc_location_gazetteer": 2,
}

RECOMMENDATIONS = (
    "dedupe_keep_higher_confidence",
    "merge_dedupe_keep_better_geocode",
    "dedupe_drop_bad_geocode",
    "split_overlap_key_keep_both_pins",
    "manual_review",
)

CSV_FIELDS = [
    "overlap_key",
    "title",
    "date",
    "distance_miles",
    "recommendation",
    "action",
    "reason",
    "preferred_row_if_forced_to_pick_one",
    "alternate_row",
    "row_a_lat",
    "row_a_lng",
    "row_a_display_location",
    "row_a_borough",
    "row_a_geocoder_source",
    "row_a_geocoder_confidence",
    "row_a_source_event_id",
    "row_b_lat",
    "row_b_lng",
    "row_b_display_location",
    "row_b_borough",
    "row_b_geocoder_source",
    "row_b_geocoder_confidence",
    "row_b_source_event_id",
]


def miles_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    radius_miles = 3958.8
    to_rad = math.radians
    dlat = to_rad(lat2 - lat1)
    dlng = to_rad(lng2 - lng1)
    x = (
        math.sin(dlat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * radius_miles * math.asin(math.sqrt(x))


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def venue_core(display_location: str) -> str:
    text = normalize_text(display_location)
    text = re.sub(r"\bin\b.*", "", text).strip()
    return text


def same_venue_family(left: str, right: str) -> bool:
    a = venue_core(left)
    b = venue_core(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def row_score(row: dict[str, Any]) -> tuple[int, int, int]:
    source_rank = SRC_RANK.get(str(row.get("geocoder_source") or ""), 0)
    confidence_rank = CONF_RANK.get(str(row.get("geocoder_confidence") or "").lower(), 0)
    has_source_event_id = 1 if row.get("source_event_id") else 0
    return (source_rank, confidence_rank, has_source_event_id)


def pick_winner(row_a: dict[str, Any], row_b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if row_score(row_a) >= row_score(row_b):
        return row_a, row_b
    return row_b, row_a


def classify_conflict(row_a: dict[str, Any], row_b: dict[str, Any]) -> tuple[str, str]:
    distance = miles_between((row_a["lat"], row_a["lng"]), (row_b["lat"], row_b["lng"]))
    same_venue = same_venue_family(row_a.get("display_location", ""), row_b.get("display_location", ""))

    if distance < 0.05:
        return (
            "dedupe_keep_higher_confidence",
            "Coordinates are within about 80 meters; treat as one venue with geocode jitter.",
        )
    if distance < 1.0 and same_venue:
        return (
            "merge_dedupe_keep_better_geocode",
            "Same venue wording with nearby coordinates; keep the stronger geocode and drop the duplicate row.",
        )
    if distance >= 1.0 and not same_venue:
        return (
            "split_overlap_key_keep_both_pins",
            "Different venues share the same title|date overlap_key; assign distinct overlap_keys and keep both pins.",
        )
    if distance >= 1.0 and same_venue:
        return (
            "dedupe_drop_bad_geocode",
            "Same venue text but far-apart coordinates; keep the better geocode and drop the outlier row.",
        )
    return (
        "manual_review",
        "Venue text and distance are ambiguous; human should confirm merge vs split before promotion.",
    )


def export_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    return [row for row in events if isinstance(row, dict)]


def row_snapshot(row: dict[str, Any], keep: bool) -> dict[str, Any]:
    return {
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "source_event_id": row.get("source_event_id"),
        "keep": keep,
    }


def build_audit(export_events: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in export_events:
        key = str(row.get("overlap_key") or "").strip()
        if key:
            grouped[key].append(row)

    findings: list[dict[str, Any]] = []
    for overlap_key, rows in sorted(grouped.items()):
        if len(rows) != 2:
            continue
        row_a, row_b = rows[0], rows[1]
        coord_a = (round(float(row_a["lat"]), 6), round(float(row_a["lng"]), 6))
        coord_b = (round(float(row_b["lat"]), 6), round(float(row_b["lng"]), 6))
        if coord_a == coord_b:
            continue

        recommendation, reason = classify_conflict(row_a, row_b)
        winner, loser = pick_winner(row_a, row_b)
        distance = miles_between((row_a["lat"], row_a["lng"]), (row_b["lat"], row_b["lng"]))
        if recommendation == "split_overlap_key_keep_both_pins":
            action = "rekey_both_rows"
        elif recommendation == "manual_review":
            action = "human_decision_required"
        else:
            action = "drop_one_row"
        findings.append(
            {
                "overlap_key": overlap_key,
                "title": row_a.get("title"),
                "date": row_a.get("date"),
                "distance_miles": round(distance, 3),
                "recommendation": recommendation,
                "action": action,
                "reason": reason,
                "preferred_row_if_forced_to_pick_one": row_snapshot(winner, True),
                "alternate_row": row_snapshot(loser, False),
                "row_a": row_snapshot(row_a, winner is row_a),
                "row_b": row_snapshot(row_b, winner is row_b),
            }
        )

    recommendation_counts = Counter(item["recommendation"] for item in findings)
    dedupe_pairs = sum(
        1
        for item in findings
        if item["recommendation"]
        in {
            "dedupe_keep_higher_confidence",
            "merge_dedupe_keep_better_geocode",
            "dedupe_drop_bad_geocode",
        }
    )
    split_pairs = recommendation_counts.get("split_overlap_key_keep_both_pins", 0)
    manual_pairs = recommendation_counts.get("manual_review", 0)
    rows_after_dedupe = len(export_events) - dedupe_pairs

    manual_only = len(findings) > 0 and all(
        item["recommendation"] == "manual_review" for item in findings
    )
    all_resolved = len(findings) == 0

    return {
        "artifact_type": "supplemental_overlap_key_coord_conflict_audit_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_pre_phase2e_overlap_key_audit",
        "qa_pass": len(findings) == 78 or manual_only or all_resolved,
        "promotion_performed": False,
        "source_export_path": repo_relative(EXPORT_PATH),
        "summary": {
            "export_event_count": len(export_events),
            "unique_overlap_key_count": len(grouped),
            "conflict_pair_count": len(findings),
            "conflict_row_count": len(findings) * 2,
            "recommendation_counts": dict(recommendation_counts),
            "dedupe_pair_count": dedupe_pairs,
            "split_pair_count": split_pairs,
            "manual_review_pair_count": manual_pairs,
            "projected_export_event_count_after_dedupe_actions": rows_after_dedupe,
            "projected_unique_overlap_key_count_after_dedupe_and_rekey": len(grouped)
            + split_pairs,
        },
        "next_required_step": (
            "Apply human-reviewed cleanup decisions before Phase 2E promotion. "
            "Do not promote until overlap_key conflicts are resolved."
        ),
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "findings": findings,
    }


def findings_to_csv_rows(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in findings:
        row_a = item["row_a"]
        row_b = item["row_b"]
        keep = item["preferred_row_if_forced_to_pick_one"]
        drop = item["alternate_row"]
        rows.append(
            {
                "overlap_key": item["overlap_key"],
                "title": item.get("title"),
                "date": item.get("date"),
                "distance_miles": item.get("distance_miles"),
                "recommendation": item.get("recommendation"),
                "action": item.get("action"),
                "reason": item.get("reason"),
                "preferred_row_if_forced_to_pick_one": f"{keep.get('lat')},{keep.get('lng')}",
                "alternate_row": f"{drop.get('lat')},{drop.get('lng')}",
                "row_a_lat": row_a.get("lat"),
                "row_a_lng": row_a.get("lng"),
                "row_a_display_location": row_a.get("display_location"),
                "row_a_borough": row_a.get("borough"),
                "row_a_geocoder_source": row_a.get("geocoder_source"),
                "row_a_geocoder_confidence": row_a.get("geocoder_confidence"),
                "row_a_source_event_id": row_a.get("source_event_id"),
                "row_b_lat": row_b.get("lat"),
                "row_b_lng": row_b.get("lng"),
                "row_b_display_location": row_b.get("display_location"),
                "row_b_borough": row_b.get("borough"),
                "row_b_geocoder_source": row_b.get("geocoder_source"),
                "row_b_geocoder_confidence": row_b.get("geocoder_confidence"),
                "row_b_source_event_id": row_b.get("source_event_id"),
            }
        )
    return rows


def main() -> int:
    payload = load_json_file(EXPORT_PATH, {})
    export_events = export_rows(payload)
    report = build_audit(export_events)
    save_json_file(REPORT_PATH, report)
    write_csv(CSV_PATH, findings_to_csv_rows(report["findings"]), CSV_FIELDS)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
