#!/usr/bin/env python3
"""Geocode unlinked Access Benefits services rows for supplemental intake.

Targets calendar-only services events that appear list-only in discovery review
but were never ingested into supplemental queues. Writes geocode proposals and
appends filled rows to supplemental_calendar_only_review_queue.json as pending.

Does NOT approve rows, modify location_cache.json, or publish to feeds=main.
"""

from __future__ import annotations

import argparse
import json
import os
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
    from scripts.nyc_geoclient_client import NYCGeoclientClient
    from scripts.nyc_location_gazetteer import (
        GAZETTEER_PATH,
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
    )
    from scripts.nyc_location_resolver import NYCLocationResolver
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
    from nyc_geoclient_client import NYCGeoclientClient
    from nyc_location_gazetteer import (
        GAZETTEER_PATH,
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
    )
    from nyc_location_resolver import NYCLocationResolver

CALENDAR_SNAPSHOT = DATA_DIR / "nyc_citywide_events_calendar_snapshot.json"
CALENDAR_QUEUE = DATA_DIR / "supplemental_calendar_only_review_queue.json"
PROPOSALS_PATH = DATA_DIR / "staging" / "access_benefits_geocode_proposals.json"
REPORT_PATH = DATA_DIR / "reports" / "access_benefits_geocode_report.json"

# Canonical source_event_id per near-duplicate cluster (Riverside, Butler).
TARGET_SOURCE_EVENT_IDS = (
    "1116816",  # Fair Fares Manhattan
    "1116836",  # Fair Fares Queens
    "1117076",  # Fair Fares Brooklyn
    "1116776",  # Riverside Church Food Pantry
    "1116636",  # Butler Houses NeighborhoodStat
    "1116736",  # Jonas Bronck Apartments seniors
    "1116876",  # Johnson Houses NeighborhoodStat
    "1116896",  # NYPL SNF Library office hours
)


def load_calendar_rows() -> dict[str, dict[str, Any]]:
    payload = load_json_file(CALENDAR_SNAPSHOT, [])
    rows = payload if isinstance(payload, list) else payload.get("events") or []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        seid = str(row.get("source_event_id") or "").strip()
        if seid:
            indexed[seid] = row
    return indexed


def calendar_to_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    boroughs = row.get("boroughs") or []
    borough = ", ".join(str(value) for value in boroughs if value)
    address = str(row.get("address") or "").strip() or "Location TBA"
    title = str(row.get("title") or "")
    start = row.get("start_date_time")
    queue_row = {
        "address": address,
        "boroughs": boroughs,
        "categories": row.get("categories") or [],
        "display_location": address,
        "borough": borough,
        "overlap_key": overlap_key(title, start),
        "permalink": row.get("permalink"),
        "review_reason": "calendar_title_date_key_not_in_permit_pipeline",
        "source_dataset": row.get("source_dataset") or "nyc-citywide-events-calendar-api",
        "source_event_id": row.get("source_event_id"),
        "start_date_time": start,
        "title": title,
        "manual_review_status": "pending",
        "parks_title_date_match": False,
        "production_feed": False,
        "promotion_allowed": False,
    }
    queue_row.update(safety_fields())
    return queue_row


def load_resolver(*, allow_live_geosearch: bool) -> tuple[NYCLocationResolver, Any, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        save_json_file(GAZETTEER_PATH, build_gazetteer_index())
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    cache = load_json_file(GEOSEARCH_CACHE_PATH, {})
    entries = cache.get("entries", {}) if isinstance(cache, dict) else {}
    resolver = NYCLocationResolver(gazetteer, entries, allow_live_geosearch=allow_live_geosearch)
    geoclient = NYCGeoclientClient.load_default(allow_live=allow_live_geosearch)
    parks_overlap = build_calendar_parks_overlap_index()
    parks_properties = load_parks_properties_name_index()
    return resolver, geoclient, parks_overlap, parks_properties


def geocode_targets(*, allow_live_geosearch: bool, write_queue: bool) -> dict[str, Any]:
    calendar = load_calendar_rows()
    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        save_json_file(GAZETTEER_PATH, build_gazetteer_index())
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    resolver, geoclient, parks_overlap, parks_properties = load_resolver(
        allow_live_geosearch=allow_live_geosearch
    )
    proposals: list[dict[str, Any]] = []
    filled = 0
    missing = 0

    queue_payload = load_json_file(CALENDAR_QUEUE, {})
    queue_rows = queue_payload.get("review_queue") if isinstance(queue_payload, dict) else []
    if not isinstance(queue_rows, list):
        queue_rows = []
    existing_ids = {
        str(row.get("source_event_id") or "")
        for row in queue_rows
        if isinstance(row, dict) and row.get("source_event_id")
    }

    for seid in TARGET_SOURCE_EVENT_IDS:
        source_row = calendar.get(seid)
        if not source_row:
            missing += 1
            proposals.append({"source_event_id": seid, "status": "missing_from_calendar_snapshot"})
            continue
        queue_row = calendar_to_queue_row(source_row)
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
            "title": queue_row.get("title"),
            "date": date_key(queue_row.get("start_date_time")),
            "address": queue_row.get("address"),
            "status": "filled" if fill else "unfilled",
            "fill": fill,
        }
        proposals.append(proposal)
        if not fill:
            continue
        filled += 1
        lat = fill.get("proposed_lat")
        lng = fill.get("proposed_lng")
        if not valid_nyc_lat_lng(lat, lng):
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
            }
        )
        if seid not in existing_ids:
            queue_rows.append(queue_row)
            existing_ids.add(seid)

    if write_queue and allow_live_geosearch:
        resolver.save_geosearch_cache()

    if write_queue:
        queue_payload = {
            "artifact_type": "supplemental_calendar_only_review_queue",
            "generated_at_utc": utc_now_iso(),
            "review_queue": queue_rows,
        }
        save_json_file(CALENDAR_QUEUE, queue_payload)

    report = {
        "artifact_type": "access_benefits_geocode_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_access_benefits_geocode",
        "qa_pass": filled == len(TARGET_SOURCE_EVENT_IDS),
        "target_count": len(TARGET_SOURCE_EVENT_IDS),
        "filled_count": filled,
        "missing_from_snapshot_count": missing,
        "allow_live_geosearch": allow_live_geosearch,
        "queue_path": repo_relative(CALENDAR_QUEUE),
        "proposals_path": repo_relative(PROPOSALS_PATH),
        "proposals": proposals,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
            "manual_review_status": "pending",
        },
    }
    save_json_file(PROPOSALS_PATH, {
        "artifact_type": "access_benefits_geocode_proposals",
        "generated_at_utc": report["generated_at_utc"],
        "proposals": proposals,
    })
    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write calendar queue")
    parser.add_argument(
        "--allow-live-geosearch",
        action="store_true",
        help="Allow live NYC GeoSearch / Geoclient calls",
    )
    args = parser.parse_args()
    allow_live = args.allow_live_geosearch or os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    report = geocode_targets(allow_live_geosearch=allow_live, write_queue=not args.dry_run)
    print(json.dumps({
        "qa_pass": report["qa_pass"],
        "filled_count": report["filled_count"],
        "target_count": report["target_count"],
        "report": repo_relative(REPORT_PATH),
    }, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
