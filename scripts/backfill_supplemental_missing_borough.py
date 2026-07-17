#!/usr/bin/env python3
"""Backfill missing borough on approved supplemental queue rows from trusted sources.

Resolution order (no invented boroughs):
1. NYC Parks properties reference (park parent / display location)
2. Supplemental location memory (approved-row memory with borough set)
3. Supplemental gazetteer overlay borough field
4. Sibling approved queue rows sharing the same display_location
5. Official venue-name borough prefix in display_location (e.g. Queens Public Library)
6. NYC Parks properties point-in-polygon at approved coordinates
7. NYC GeoSearch reverse at approved coordinates (cache first, then live)

Does NOT promote, set promotion_allowed=true, or modify location_cache.json
or public map feeds.

Outputs:
- data/supplemental_manual_approval_queue.json (patched in place)
- data/reports/supplemental_borough_backfill_report.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

try:
    from scripts.build_supplemental_pin_quality_review_report import parent_park_from_display
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        load_supplemental_gazetteer_overlay,
        SUPPLEMENTAL_OVERLAY_PATH,
    )
    from scripts.geojson_polygon_utils import find_park_property_row, point_in_polygon_geometry
    from scripts.supplemental_location_memory_utils import load_memory_entries
except ModuleNotFoundError:  # pragma: no cover
    from build_supplemental_pin_quality_review_report import parent_park_from_display
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        load_parks_properties_name_index,
        parse_facility_in_parent,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from gps_identity import normalize_text_legacy
    from nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        load_supplemental_gazetteer_overlay,
        SUPPLEMENTAL_OVERLAY_PATH,
    )
    from geojson_polygon_utils import find_park_property_row, point_in_polygon_geometry
    from supplemental_location_memory_utils import load_memory_entries

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_borough_backfill_report.json"

QUEUE_BOROUGH_ABBREVS = frozenset({"Mn", "Bk", "Qn", "Bx", "SI", "Other"})
FULL_BOROUGH_TO_QUEUE = {
    "manhattan": "Mn",
    "brooklyn": "Bk",
    "queens": "Qn",
    "bronx": "Bx",
    "staten island": "SI",
}

# Official venue-name prefixes present in NYC Parks BigApps display_location text.
DISPLAY_VENUE_BOROUGH_PREFIXES: tuple[tuple[str, str], ...] = (
    ("queens public library", "Qn"),
    ("brooklyn public library", "Bk"),
    ("bronx library", "Bx"),
    ("staten island", "SI"),
    ("manhattan", "Mn"),
)


def borough_from_display_venue_prefix(display: str) -> str | None:
    norm = normalize_text_legacy(display)
    for prefix, borough in DISPLAY_VENUE_BOROUGH_PREFIXES:
        if norm.startswith(prefix):
            return borough
    return None


def load_parks_properties_rows() -> list[dict[str, Any]]:
    payload = load_json_file(DATA_DIR / "nyc_parks_properties_reference.json", {})
    properties = payload.get("properties") if isinstance(payload, dict) else payload
    if not isinstance(properties, list):
        return []
    return [row for row in properties if isinstance(row, dict)]


def lookup_borough_point_in_park_polygon(
    row: dict[str, Any],
    parks_properties: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    lat = row.get("proposed_lat", row.get("lat"))
    lng = row.get("proposed_lng", row.get("lng"))
    if not valid_nyc_lat_lng(lat, lng):
        return None, None
    lat_f = float(lat)
    lng_f = float(lng)
    for prop in parks_properties:
        geometry = prop.get("geometry") or prop.get("multipolygon")
        if not isinstance(geometry, dict):
            continue
        if not point_in_polygon_geometry(lng_f, lat_f, geometry):
            continue
        borough = parks_borough_from_property(prop)
        if borough:
            park_name = str(prop.get("signname") or prop.get("name311") or "")
            return borough, f"nyc_parks_properties_reference:point_in_polygon:{park_name}"
    return None, None


def lookup_borough_geosearch_reverse(
    row: dict[str, Any],
    *,
    geosearch_cache: dict[str, Any],
) -> tuple[str | None, str | None]:
    lat = row.get("proposed_lat", row.get("lat"))
    lng = row.get("proposed_lng", row.get("lng"))
    if not valid_nyc_lat_lng(lat, lng):
        return None, None
    lat_f = float(lat)
    lng_f = float(lng)

    entries = geosearch_cache.get("entries", {}) if isinstance(geosearch_cache, dict) else {}
    if isinstance(entries, dict):
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            try:
                entry_lat = float(entry["lat"])
                entry_lng = float(entry["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(entry_lat - lat_f) < 1e-5 and abs(entry_lng - lng_f) < 1e-5:
                borough = queue_borough_from_source(entry.get("borough"))
                if borough:
                    return borough, "nyc_geosearch_gazetteer_cache"

    try:
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode({"point.lat": lat_f, "point.lon": lng_f})
        url = f"https://geosearch.planninglabs.nyc/v2/reverse?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "nycif-live-feeds/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        features = payload.get("features", []) if isinstance(payload, dict) else []
        if features and isinstance(features[0], dict):
            borough_label = features[0].get("properties", {}).get("borough")
            borough = queue_borough_from_source(borough_label)
            if borough:
                return borough, "nyc_geosearch_planninglabs_reverse"
    except Exception:
        return None, None
    return None, None

def queue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("approval_queue"), list):
        return [row for row in payload["approval_queue"] if isinstance(row, dict)]
    return []


def queue_borough_from_source(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in QUEUE_BOROUGH_ABBREVS:
        return raw
    mapped = FULL_BOROUGH_TO_QUEUE.get(normalize_text_legacy(raw))
    return mapped


def parks_borough_from_property(row: dict[str, Any]) -> str | None:
    return queue_borough_from_source(row.get("borough_label") or row.get("borough"))


def lookup_parks_borough(
    display: str,
    parks_index: dict[str, list[dict[str, Any]]],
) -> str | None:
    parent = parent_park_from_display(display) or display
    prop = find_park_property_row(parent, None, parks_index)
    if prop:
        borough = parks_borough_from_property(prop)
        if borough:
            return borough

    decomposed = parse_facility_in_parent(display)
    if decomposed:
        prop = find_park_property_row(decomposed[1], None, parks_index)
        if prop:
            borough = parks_borough_from_property(prop)
            if borough:
                return borough
    return None


def build_memory_display_index(
    memory_entries: dict[str, dict[str, Any]],
) -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in memory_entries.values():
        display = str(entry.get("display_location") or "").strip()
        borough = queue_borough_from_source(entry.get("borough"))
        if display and borough:
            index[normalize_text_legacy(display)] = borough
    return index


def build_sibling_borough_index(queue: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in queue:
        display = str(row.get("display_location") or "").strip()
        borough = queue_borough_from_source(row.get("borough"))
        if display and borough:
            index[normalize_text_legacy(display)] = borough
    return index


def resolve_borough(
    row: dict[str, Any],
    *,
    parks_index: dict[str, list[dict[str, Any]]],
    parks_properties: list[dict[str, Any]],
    memory_display_index: dict[str, str],
    gazetteer: NYCLocationGazetteer,
    sibling_index: dict[str, str],
    geosearch_cache: dict[str, Any],
) -> tuple[str | None, str | None]:
    display = str(row.get("display_location") or "").strip()
    if not display:
        return None, None

    parks_borough = lookup_parks_borough(display, parks_index)
    if parks_borough:
        return parks_borough, "nyc_parks_properties_reference"

    memory_borough = memory_display_index.get(normalize_text_legacy(display))
    if memory_borough:
        return memory_borough, "supplemental_location_memory"

    hit = gazetteer.lookup_display(display, None)
    if hit:
        overlay_borough = queue_borough_from_source(hit.get("borough"))
        if overlay_borough:
            return overlay_borough, "supplemental_location_gazetteer_overlay"

    sibling_borough = sibling_index.get(normalize_text_legacy(display))
    if sibling_borough:
        return sibling_borough, "sibling_approved_row"

    prefix_borough = borough_from_display_venue_prefix(display)
    if prefix_borough:
        return prefix_borough, "nyc_parks_bigapps_events_snapshot:venue_name_prefix"

    polygon_borough, polygon_source = lookup_borough_point_in_park_polygon(row, parks_properties)
    if polygon_borough and polygon_source:
        return polygon_borough, polygon_source

    geosearch_borough, geosearch_source = lookup_borough_geosearch_reverse(
        row,
        geosearch_cache=geosearch_cache,
    )
    if geosearch_borough and geosearch_source:
        return geosearch_borough, geosearch_source

    return None, None


def apply_backfill(queue: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parks_index = load_parks_properties_name_index()
    parks_properties = load_parks_properties_rows()
    memory_display_index = build_memory_display_index(load_memory_entries())
    gazetteer = NYCLocationGazetteer(load_supplemental_gazetteer_overlay(SUPPLEMENTAL_OVERLAY_PATH))
    sibling_index = build_sibling_borough_index(queue)
    geosearch_cache = load_json_file(GEOSEARCH_CACHE_PATH, {})

    source_counts: Counter[str] = Counter()
    unresolved_displays: Counter[str] = Counter()
    backfilled_at = utc_now_iso()
    updated_queue: list[dict[str, Any]] = []

    candidates = [
        row
        for row in queue
        if str(row.get("manual_review_status") or "").lower() == "approved"
        and not queue_borough_from_source(row.get("borough"))
    ]

    for row in queue:
        patched = dict(row)
        if str(patched.get("manual_review_status") or "").lower() != "approved":
            updated_queue.append(patched)
            continue
        if queue_borough_from_source(patched.get("borough")):
            updated_queue.append(patched)
            continue

        borough, source = resolve_borough(
            patched,
            parks_index=parks_index,
            parks_properties=parks_properties,
            memory_display_index=memory_display_index,
            gazetteer=gazetteer,
            sibling_index=sibling_index,
            geosearch_cache=geosearch_cache,
        )
        if borough and source:
            patched["borough"] = borough
            patched["borough_backfill_source"] = source
            patched["borough_backfill_at_utc"] = backfilled_at
            source_counts[source] += 1
        else:
            display = str(patched.get("display_location") or "").strip() or "(empty display)"
            unresolved_displays[display] += 1
        updated_queue.append(patched)

    report = {
        "artifact_type": "supplemental_borough_backfill_report",
        "generated_at_utc": backfilled_at,
        "phase": "m11_supplemental_borough_backfill",
        "source_queue_path": repo_relative(APPROVAL_QUEUE_PATH),
        "candidate_count": len(candidates),
        "backfilled_count": sum(source_counts.values()),
        "unresolved_count": sum(unresolved_displays.values()),
        "source_counts": dict(source_counts),
        "unresolved_display_counts": dict(unresolved_displays.most_common()),
        "qa_pass": sum(unresolved_displays.values()) == 0,
        "safety": {
            "promotion_allowed": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "production_feed": False,
        },
        "next_required_step": (
            "Re-run dry_run_supplemental_phase2e_promotion.py and rebuild export feed. "
            "Unresolved rows need manual borough review; do not invent boroughs."
        ),
    }
    return updated_queue, report


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = queue_rows(payload)
    updated_queue, report = apply_backfill(queue)

    if isinstance(payload, dict):
        payload = dict(payload)
        payload["approval_queue"] = updated_queue
        save_json_file(APPROVAL_QUEUE_PATH, payload)
    else:
        save_json_file(APPROVAL_QUEUE_PATH, {"approval_queue": updated_queue})

    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
