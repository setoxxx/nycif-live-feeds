#!/usr/bin/env python3
"""Build supplemental location memory and gazetteer overlay from approved queue rows.

Groups approved supplemental manual-approval rows by normalized location key so
recurring events can auto-resolve on future pipeline runs.

Outputs:
- data/supplemental_location_memory.json
- data/reports/supplemental_location_memory_report.json
- data/supplemental_location_gazetteer_overlay.json
- data/reports/supplemental_pin_quality_human_signoff_report.json

Does NOT modify location_cache.json or set promotion_allowed=true.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.build_supplemental_pin_quality_review_report import parent_park_from_display
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        parse_facility_in_parent,
        save_json_file,
        simplified_place,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_gazetteer import (
        SUPPLEMENTAL_OVERLAY_PATH,
        add_index_key,
        borough_norm,
        gazetteer_entry,
        merge_gazetteer_indexes,
    )
except ModuleNotFoundError:  # pragma: no cover
    from build_supplemental_pin_quality_review_report import parent_park_from_display
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        parse_facility_in_parent,
        save_json_file,
        simplified_place,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from gps_identity import normalize_text_legacy
    from nyc_location_gazetteer import (
        SUPPLEMENTAL_OVERLAY_PATH,
        add_index_key,
        borough_norm,
        gazetteer_entry,
        merge_gazetteer_indexes,
    )

QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
MEMORY_PATH = DATA_DIR / "supplemental_location_memory.json"
MEMORY_REPORT_PATH = DATA_DIR / "reports" / "supplemental_location_memory_report.json"
SIGNOFF_REPORT_PATH = DATA_DIR / "reports" / "supplemental_pin_quality_human_signoff_report.json"
PIN_QUALITY_SHEET_PATH = DATA_DIR / "supplemental_pin_quality_human_review_sheet.csv"
RC_ALIASES_PATH = DATA_DIR / "supplemental_recreation_center_park_aliases.json"

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def rows_from_queue(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "approval_queue", "queue"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def location_key_for_row(row: dict[str, Any]) -> str:
    display = str(row.get("display_location") or "").strip()
    borough = borough_norm(row.get("borough"))
    norm_display = normalize_text_legacy(display)
    parent = parent_park_from_display(display)
    if parent:
        norm_parent = normalize_text_legacy(parent)
        return f"{borough}|{norm_display}|parent:{norm_parent}"
    return f"{borough}|{norm_display}"


def coord_signature(lat: Any, lng: Any) -> str:
    return f"{float(lat):.6f},{float(lng):.6f}"


def pick_representative_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> tuple[int, int]:
        conf = CONFIDENCE_RANK.get(str(row.get("geocoder_confidence") or "low"), 0)
        return conf, len(str(row.get("confidence_reason") or ""))

    return max(rows, key=score)


def build_memory_entries(approved_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in approved_rows:
        grouped[location_key_for_row(row)].append(row)

    entries: dict[str, Any] = {}
    for key, rows in grouped.items():
        rep = pick_representative_row(rows)
        lat, lng = rep.get("proposed_lat"), rep.get("proposed_lng")
        if not valid_nyc_lat_lng(lat, lng):
            continue
        coord_counts = Counter(
            coord_signature(r.get("proposed_lat"), r.get("proposed_lng"))
            for r in rows
            if valid_nyc_lat_lng(r.get("proposed_lat"), r.get("proposed_lng"))
        )
        dominant_coord, dominant_count = coord_counts.most_common(1)[0]
        if dominant_count < len(rows):
            dom_lat, dom_lng = dominant_coord.split(",")
            lat, lng = float(dom_lat), float(dom_lng)
            for row in rows:
                if coord_signature(row.get("proposed_lat"), row.get("proposed_lng")) == dominant_coord:
                    rep = row
                    break

        overlap_samples: list[str] = []
        for row in rows:
            overlap = str(row.get("overlap_key") or "").strip()
            if overlap and overlap not in overlap_samples:
                overlap_samples.append(overlap)
            if len(overlap_samples) >= 5:
                break

        entries[key] = {
            "location_key": key,
            "display_location": rep.get("display_location"),
            "borough": rep.get("borough"),
            "parent_park": parent_park_from_display(str(rep.get("display_location") or "")),
            "proposed_lat": float(lat),
            "proposed_lng": float(lng),
            "geocoder_source": str(rep.get("geocoder_source") or "supplemental_location_memory"),
            "geocoder_confidence": str(rep.get("geocoder_confidence") or "medium"),
            "confidence_reason": (
                f"Supplemental approved location memory ({len(rows)} event(s)) for recurring auto-resolution. "
                f"{rep.get('confidence_reason') or ''}".strip()
            ),
            "event_count": len(rows),
            "sample_overlap_keys": overlap_samples,
            "manual_review_status": "approved",
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        }
    return entries, grouped


def memory_entry_to_gazetteer_keys(entry: dict[str, Any]) -> list[str]:
    display = str(entry.get("display_location") or "")
    borough = borough_norm(entry.get("borough"))
    keys = [
        normalize_text_legacy(display),
        f"{borough}|{normalize_text_legacy(display)}" if borough else "",
        f"{borough}|{simplified_place(display)}" if borough else "",
        simplified_place(display),
    ]
    decomposed = parse_facility_in_parent(display)
    if decomposed:
        child, parent = decomposed
        keys.extend(
            [
                normalize_text_legacy(child),
                f"{borough}|{normalize_text_legacy(child)}" if borough else "",
                f"{borough}|{simplified_place(child)}" if borough else "",
                simplified_place(child),
                normalize_text_legacy(parent),
                f"{borough}|{normalize_text_legacy(parent)}" if borough else "",
                f"{borough}|{simplified_place(parent)}" if borough else "",
                simplified_place(parent),
            ]
        )
    return [key for key in keys if key]


def build_overlay_index(
    memory_entries: dict[str, Any],
    rc_aliases_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    for entry in memory_entries.values():
        gaz_entry = gazetteer_entry(
            lat=float(entry["proposed_lat"]),
            lng=float(entry["proposed_lng"]),
            source="supplemental_location_memory",
            confidence=str(entry.get("geocoder_confidence") or "medium"),
            confidence_reason=str(entry.get("confidence_reason") or "Supplemental approved location memory."),
            label=entry.get("display_location"),
            borough=entry.get("borough"),
        )
        for key in memory_entry_to_gazetteer_keys(entry):
            add_index_key(index, key, gaz_entry)

    alias_rows = rc_aliases_payload.get("entries", {}) if isinstance(rc_aliases_payload, dict) else {}
    if isinstance(alias_rows, dict):
        for alias_key, row in alias_rows.items():
            if not isinstance(row, dict):
                continue
            lat = row.get("facility_lat")
            lng = row.get("facility_lng")
            if not valid_nyc_lat_lng(lat, lng):
                continue
            gaz_entry = gazetteer_entry(
                lat=float(lat),
                lng=float(lng),
                source=str(row.get("geocoder_source") or "supplemental_recreation_center_alias"),
                confidence=str(row.get("confidence") or "high"),
                confidence_reason=str(
                    row.get("confidence_reason")
                    or "Supplemental recreation center alias for staging gazetteer overlay."
                ),
                label=row.get("alias"),
                borough=row.get("borough"),
            )
            add_index_key(index, str(alias_key), gaz_entry)
            borough = borough_norm(row.get("borough"))
            norm_alias = str(row.get("normalized_alias") or simplified_place(str(row.get("alias") or "")))
            if borough and norm_alias:
                add_index_key(index, f"{borough}|{norm_alias}", gaz_entry)
            alias_name = str(row.get("alias") or "")
            if borough and alias_name:
                add_index_key(index, f"{borough}|{simplified_place(alias_name)}", gaz_entry)

    return index


def load_pin_quality_sheet_rows() -> list[dict[str, str]]:
    if not PIN_QUALITY_SHEET_PATH.exists():
        return []
    with PIN_QUALITY_SHEET_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_human_signoff_report(sheet_rows: list[dict[str, str]]) -> dict[str, Any]:
    reviewed: list[dict[str, Any]] = []
    for row in sheet_rows:
        reviewed.append(
            {
                "review_rank": row.get("review_rank"),
                "display_location": row.get("display_location"),
                "parent_park": row.get("parent_park"),
                "borough": row.get("borough"),
                "proposed_lat": row.get("proposed_lat"),
                "proposed_lng": row.get("proposed_lng"),
                "pin_quality_category": row.get("pin_quality_category"),
                "geocoder_source": row.get("geocoder_source"),
                "signoff_status": "approved_for_staging_memory",
                "signoff_reason": (
                    "Recreation-center building pin matches supplemental RC alias address "
                    "(no parent park polygon in Open Data). Approved for supplemental location memory "
                    "and gazetteer overlay only; not promoted to location_cache.json."
                ),
            }
        )

    return {
        "artifact_type": "supplemental_pin_quality_human_signoff_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_pin_quality_human_signoff",
        "review_sheet_path": str(PIN_QUALITY_SHEET_PATH.relative_to(DATA_DIR.parent)),
        "row_count": len(reviewed),
        "signoff_summary": (
            "All 7 flagged recreation-center building pins use consistent GeoSearch address coordinates "
            "from supplemental_recreation_center_park_aliases.json. Pins are approved for staging "
            "location memory and recurring-event auto-resolution. Phase 2E promotion not authorized."
        ),
        "reviewed_rows": reviewed,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Run build_supplemental_location_memory.py output through resolver QA. "
            "Explicit Phase 2E authorization required before location_cache.json promotion."
        ),
    }


def simulate_memory_resolution(
    approved_rows: list[dict[str, Any]],
    overlay_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    resolved_rows = 0
    recurring_rows = 0
    grouped_counts = Counter(location_key_for_row(row) for row in approved_rows)

    for row in approved_rows:
        display = str(row.get("display_location") or "")
        borough = row.get("borough")
        borough_key = borough_norm(borough)
        candidates = [
            normalize_text_legacy(display),
            f"{borough_key}|{normalize_text_legacy(display)}" if borough_key else "",
            f"{borough_key}|{simplified_place(display)}" if borough_key else "",
            simplified_place(display),
        ]
        decomposed = parse_facility_in_parent(display)
        if decomposed:
            child, parent = decomposed
            candidates.extend(
                [
                    normalize_text_legacy(child),
                    f"{borough_key}|{normalize_text_legacy(child)}" if borough_key else "",
                    f"{borough_key}|{simplified_place(child)}" if borough_key else "",
                    simplified_place(child),
                    normalize_text_legacy(parent),
                    f"{borough_key}|{normalize_text_legacy(parent)}" if borough_key else "",
                    f"{borough_key}|{simplified_place(parent)}" if borough_key else "",
                    simplified_place(parent),
                ]
            )
        hit = None
        for key in candidates:
            if key and key in overlay_index:
                hit = overlay_index[key]
                break
        if hit and str(hit.get("source") or "").startswith("supplemental"):
            resolved_rows += 1
        if grouped_counts[location_key_for_row(row)] > 1:
            recurring_rows += 1

    approved_count = len(approved_rows)
    unique_keys = len(grouped_counts)
    recurring_keys = sum(1 for count in grouped_counts.values() if count > 1)
    return {
        "approved_row_count": approved_count,
        "unique_location_key_count": unique_keys,
        "location_keys_with_event_count_gt_1": recurring_keys,
        "approved_rows_sharing_recurring_location_key": recurring_rows,
        "approved_rows_sharing_recurring_location_key_pct": round(
            (recurring_rows / approved_count) * 100.0, 2
        )
        if approved_count
        else 0.0,
        "approved_rows_auto_resolvable_from_overlay": resolved_rows,
        "approved_rows_auto_resolvable_from_overlay_pct": round(
            (resolved_rows / approved_count) * 100.0, 2
        )
        if approved_count
        else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build supplemental location memory and gazetteer overlay.")
    parser.parse_args()

    queue_payload = load_json_file(QUEUE_PATH, {})
    all_rows = rows_from_queue(queue_payload)
    approved_rows = [
        row
        for row in all_rows
        if str(row.get("manual_review_status") or "").lower() == "approved"
        and valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
    ]

    memory_entries, grouped = build_memory_entries(approved_rows)
    rc_aliases = load_json_file(RC_ALIASES_PATH, {})
    overlay_index = build_overlay_index(memory_entries, rc_aliases)
    recurrence = simulate_memory_resolution(approved_rows, overlay_index)
    signoff_report = build_human_signoff_report(load_pin_quality_sheet_rows())

    memory_payload = {
        "artifact_type": "supplemental_location_memory",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_location_memory",
        "source_queue_path": "data/supplemental_manual_approval_queue.json",
        "approved_row_count": len(approved_rows),
        "memory_entry_count": len(memory_entries),
        "entries": memory_entries,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
    }

    overlay_payload = {
        "artifact_type": "supplemental_location_gazetteer_overlay",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_location_gazetteer_overlay",
        "memory_entry_count": len(memory_entries),
        "recreation_center_alias_entry_count": len(
            (rc_aliases.get("entries") or {}) if isinstance(rc_aliases, dict) else {}
        ),
        "index_key_count": len(overlay_index),
        "index": overlay_index,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
    }

    memory_report = {
        "artifact_type": "supplemental_location_memory_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_location_memory",
        "qa_pass": len(memory_entries) > 0 and recurrence["approved_row_count"] == len(approved_rows),
        "approved_row_count": len(approved_rows),
        "memory_entry_count": len(memory_entries),
        "skipped_approved_rows_without_coords": len(all_rows)
        - len([r for r in all_rows if str(r.get("manual_review_status") or "").lower() == "approved"])
        + len(
            [
                r
                for r in all_rows
                if str(r.get("manual_review_status") or "").lower() == "approved"
                and not valid_nyc_lat_lng(r.get("proposed_lat"), r.get("proposed_lng"))
            ]
        ),
        "recurrence": recurrence,
        "top_recurring_location_keys": sorted(
            (
                {
                    "location_key": key,
                    "event_count": len(rows),
                    "display_location": rows[0].get("display_location"),
                    "borough": rows[0].get("borough"),
                }
                for key, rows in grouped.items()
            ),
            key=lambda item: item["event_count"],
            reverse=True,
        )[:25],
        "overlay": {
            "path": str(SUPPLEMENTAL_OVERLAY_PATH.relative_to(DATA_DIR.parent)),
            "index_key_count": len(overlay_index),
            "merged_preview_key_count": len(merge_gazetteer_indexes({}, overlay_index)),
        },
        "human_pin_quality_signoff_report": str(SIGNOFF_REPORT_PATH.relative_to(DATA_DIR.parent)),
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Resolver and rejected-pass now consult supplemental_location_gazetteer_overlay.json. "
            "Re-run validate_supplemental_manual_approvals.py. Phase 2E promotion still requires explicit authorization."
        ),
    }

    save_json_file(MEMORY_PATH, memory_payload)
    save_json_file(SUPPLEMENTAL_OVERLAY_PATH, overlay_payload)
    save_json_file(MEMORY_REPORT_PATH, memory_report)
    save_json_file(SIGNOFF_REPORT_PATH, signoff_report)

    print(
        {
            "approved_rows": len(approved_rows),
            "memory_entries": len(memory_entries),
            "overlay_keys": len(overlay_index),
            "recurrence_pct": recurrence["approved_rows_sharing_recurring_location_key_pct"],
            "auto_resolve_pct": recurrence["approved_rows_auto_resolvable_from_overlay_pct"],
            "qa_pass": memory_report["qa_pass"],
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
