#!/usr/bin/env python3
"""M12 geocode lane — fill list_only civic rows from missing-coordinates audit.

Targets review-feed rows (by category) that exist in the citywide calendar snapshot
but lack coordinates. Appends filled rows to supplemental_calendar_only_review_queue.json
as pending. Does NOT approve, promote, or publish to feeds=main.

Preferred batch order: market → services → volunteer → civic → housing → jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        build_calendar_parks_overlap_index,
        date_key,
        load_json_file,
        load_parks_properties_name_index,
        overlap_key,
        repo_relative,
        resolve_supplemental_coordinates,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from scripts.geocode_unlinked_access_benefits_services import (
        calendar_to_queue_row,
        load_calendar_rows,
        load_resolver,
    )
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_gazetteer import GAZETTEER_PATH, NYCLocationGazetteer
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        build_calendar_parks_overlap_index,
        date_key,
        load_json_file,
        load_parks_properties_name_index,
        overlap_key,
        repo_relative,
        resolve_supplemental_coordinates,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from geocode_unlinked_access_benefits_services import (
        calendar_to_queue_row,
        load_calendar_rows,
        load_resolver,
    )
    from nyc_location_gazetteer import GAZETTEER_PATH, NYCLocationGazetteer
    from gps_identity import normalize_text_legacy

LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"

MISSING_COORDS_PATH = DATA_DIR / "events_discovery_missing_coordinates_v02.json"
CALENDAR_QUEUE = DATA_DIR / "supplemental_calendar_only_review_queue.json"
STAGING_DIR = DATA_DIR / "staging"
REPORTS_DIR = DATA_DIR / "reports"

CIVIC_CATEGORIES = ("housing", "services", "jobs", "volunteer", "market", "civic")


def _title_norm(title: Any) -> str:
    return normalize_text_legacy(str(title or ""))


def build_location_cache_title_index() -> dict[str, dict[str, Any]]:
    payload = load_json_file(LOCATION_CACHE_PATH, {})
    entries = payload.get("entries") if isinstance(payload, dict) else {}
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(entries, dict):
        return index
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        title = entry.get("example_title")
        if not title:
            continue
        key = _title_norm(title)
        if key and key not in index and valid_nyc_lat_lng(entry.get("lat"), entry.get("lng")):
            index[key] = entry
    return index


def fill_from_location_cache_memory(
    title: str,
    cache_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    hit = cache_index.get(_title_norm(title))
    if not hit:
        return None
    lat = hit.get("lat")
    lng = hit.get("lng")
    if not valid_nyc_lat_lng(lat, lng):
        return None
    return {
        "proposed_lat": float(lat),
        "proposed_lng": float(lng),
        "geocoder_source": "location_cache_readonly_memory",
        "geocoder_confidence": "high",
        "confidence_reason": (
            f"M12 read-only location_cache memory match for '{title}'; manual review only."
        ),
        "fill_method": "location_cache_readonly_memory",
    }


def load_target_ids(*, category: str, limit: int | None = None) -> list[str]:
    payload = load_json_file(MISSING_COORDS_PATH, {})
    items = payload.get("items") if isinstance(payload, dict) else []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("current_classification") or "") != category:
            continue
        source = item.get("source_identity") if isinstance(item.get("source_identity"), dict) else {}
        seid = str(source.get("source_event_id") or "").strip()
        if seid:
            ids.append(seid)
    # Stable dedupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for seid in ids:
        if seid in seen:
            continue
        seen.add(seid)
        unique.append(seid)
    if limit is not None:
        return unique[:limit]
    return unique


def geocode_category(
    *,
    category: str,
    target_ids: list[str],
    allow_live_geosearch: bool,
    write_queue: bool,
) -> dict[str, Any]:
    calendar = load_calendar_rows()
    resolver, geoclient, parks_overlap, parks_properties = load_resolver(
        allow_live_geosearch=allow_live_geosearch
    )
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    cache_index = build_location_cache_title_index()

    queue_payload = load_json_file(CALENDAR_QUEUE, {})
    queue_rows = queue_payload.get("review_queue") if isinstance(queue_payload, dict) else []
    if not isinstance(queue_rows, list):
        queue_rows = []
    existing_ids = {
        str(row.get("source_event_id") or "")
        for row in queue_rows
        if isinstance(row, dict) and row.get("source_event_id")
    }

    proposals: list[dict[str, Any]] = []
    filled = 0
    missing = 0
    unfilled = 0
    appended = 0

    for seid in target_ids:
        source_row = calendar.get(seid)
        if not source_row:
            missing += 1
            proposals.append({"source_event_id": seid, "status": "missing_from_calendar_snapshot"})
            continue
        queue_row = calendar_to_queue_row(source_row)
        queue_row["m12_category"] = category
        fill = fill_from_location_cache_memory(str(queue_row.get("title") or ""), cache_index)
        if not fill:
            fill = resolve_supplemental_coordinates(
            queue_row,
            gazetteer,
            parks_overlap=parks_overlap,
            resolver=resolver,
            geoclient=geoclient,
            parks_properties_index=parks_properties,
            )
        proposal = {
            "source_event_id": seid,
            "category": category,
            "title": queue_row.get("title"),
            "date": date_key(queue_row.get("start_date_time")),
            "address": queue_row.get("address"),
            "status": "filled" if fill else "unfilled",
            "fill": fill,
        }
        proposals.append(proposal)
        if not fill:
            unfilled += 1
            continue
        filled += 1
        lat = fill.get("proposed_lat")
        lng = fill.get("proposed_lng")
        if not valid_nyc_lat_lng(lat, lng):
            unfilled += 1
            continue
        queue_row.update(
            {
                "proposed_lat": lat,
                "proposed_lng": lng,
                "coord_proposal_source": fill.get("geocoder_source"),
                "coord_proposal_confidence": fill.get("geocoder_confidence"),
                "coord_proposal_reason": fill.get("confidence_reason"),
                "geocoder_source": fill.get("geocoder_source"),
                "geocoder_confidence": fill.get("geocoder_confidence"),
                "confidence_reason": fill.get("confidence_reason"),
                "source_phase": "m12_geocode_list_only_civic_events",
            }
        )
        if seid not in existing_ids:
            queue_rows.append(queue_row)
            existing_ids.add(seid)
            appended += 1

    if write_queue and allow_live_geosearch:
        resolver.save_geosearch_cache()

    if write_queue:
        save_json_file(
            CALENDAR_QUEUE,
            {
                "artifact_type": "supplemental_calendar_only_review_queue",
                "generated_at_utc": utc_now_iso(),
                "review_queue": queue_rows,
            },
        )

    proposals_path = STAGING_DIR / f"m12_geocode_proposals_{category}.json"
    report_path = REPORTS_DIR / f"m12_geocode_{category}_report.json"
    report = {
        "artifact_type": "m12_geocode_list_only_civic_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m12_geocode_list_only_civic_events",
        "category": category,
        "qa_pass": filled > 0 and unfilled == 0,
        "target_count": len(target_ids),
        "filled_count": filled,
        "unfilled_count": unfilled,
        "missing_from_snapshot_count": missing,
        "appended_to_calendar_queue_count": appended,
        "allow_live_geosearch": allow_live_geosearch,
        "queue_path": repo_relative(CALENDAR_QUEUE),
        "proposals_path": repo_relative(proposals_path),
        "proposals": proposals,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
            "manual_review_status": "pending",
        },
        "next_required_step": (
            "Run build_supplemental_events_staging_feed.py then "
            "incremental_supplemental_intake.py --skip-rebuild. "
            "Do not approve until human review."
        ),
    }
    save_json_file(
        proposals_path,
        {
            "artifact_type": "m12_geocode_proposals",
            "category": category,
            "generated_at_utc": report["generated_at_utc"],
            "proposals": proposals,
        },
    )
    save_json_file(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--category",
        required=True,
        choices=CIVIC_CATEGORIES,
        help="Civic category batch from missing-coordinates audit.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on rows geocoded.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write calendar queue.")
    parser.add_argument(
        "--allow-live-geosearch",
        action="store_true",
        help="Allow live NYC GeoSearch / Geoclient calls.",
    )
    args = parser.parse_args()
    allow_live = args.allow_live_geosearch or os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    target_ids = load_target_ids(category=args.category, limit=args.limit)
    if not target_ids:
        print(json.dumps({"error": f"no target ids for category={args.category}"}, indent=2))
        return 1
    report = geocode_category(
        category=args.category,
        target_ids=target_ids,
        allow_live_geosearch=allow_live,
        write_queue=not args.dry_run,
    )
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "category": report["category"],
                "filled_count": report["filled_count"],
                "target_count": report["target_count"],
                "appended_to_calendar_queue_count": report["appended_to_calendar_queue_count"],
                "report": repo_relative(REPORTS_DIR / f"m12_geocode_{args.category}_report.json"),
            },
            indent=2,
        )
    )
    return 0 if report["filled_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
