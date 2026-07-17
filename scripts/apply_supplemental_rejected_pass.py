#!/usr/bin/env python3
"""Apply M11 supplemental rejected-row re-review pass (location resolution engine).

Uses scripts.coverage_gap_utils.resolve_supplemental_coordinates for tiered fill:
gazetteer, child-in-parent, Geoclient intersections, calendar/parks overlap, GeoSearch,
and optional park polygon pin correction.

Does NOT set promotion_allowed=true or modify location_cache.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        build_calendar_parks_overlap_index,
        is_ungeocodable_location,
        load_json_file,
        load_parks_properties_name_index,
        overlap_key,
        resolve_supplemental_coordinates,
        row_coords,
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
        is_ungeocodable_location,
        load_json_file,
        load_parks_properties_name_index,
        overlap_key,
        resolve_supplemental_coordinates,
        row_coords,
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

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
DECISIONS_PATH = DATA_DIR / "supplemental_manual_approval_decisions.json"
FILL_REPORT_PATH = DATA_DIR / "supplemental_rejected_pass_fill_report.json"
PARKS_SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"

PERMANENT_REJECT_PREFIXES = (
    "Canceled event in title",
    "Online-only event",
    "Canceled per ",
)

resolve_coordinates = resolve_supplemental_coordinates


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def is_permanent_reject(reason: str) -> bool:
    return any(str(reason or "").startswith(prefix) for prefix in PERMANENT_REJECT_PREFIXES)


def ensure_gazetteer() -> NYCLocationGazetteer:
    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        save_json_file(GAZETTEER_PATH, build_gazetteer_index())
    return NYCLocationGazetteer.from_file(GAZETTEER_PATH)


def load_resolver(*, allow_live_geosearch: bool) -> NYCLocationResolver:
    gazetteer = ensure_gazetteer()
    cache_payload = load_json_file(GEOSEARCH_CACHE_PATH, {})
    entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    return NYCLocationResolver(gazetteer, entries, allow_live_geosearch=allow_live_geosearch)


def build_parks_overlap_index() -> dict[str, dict[str, Any]]:
    payload = load_json_file(PARKS_SNAPSHOT_PATH, {})
    events = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        title = row.get("title") or ""
        start = row.get("start_date_time") or ""
        if not title or not start:
            continue
        key = overlap_key(title, start)
        lat, lng = row_coords(row)
        if valid_nyc_lat_lng(lat, lng):
            index[key] = row
    return index


def patch_queue_row(row: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["proposed_lat"] = fill["proposed_lat"]
    out["proposed_lng"] = fill["proposed_lng"]
    out["geocoder_source"] = fill["geocoder_source"]
    out["geocoder_confidence"] = fill["geocoder_confidence"]
    out["confidence_reason"] = fill["confidence_reason"]
    out["has_coordinates"] = True
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    out["promotion_allowed"] = False
    return out


def approval_reason(row: dict[str, Any], fill: dict[str, Any]) -> str:
    intake = row.get("intake_type") or ""
    fill_method = str(fill.get("fill_method") or "")
    if fill_method == "nyc_geoclient_intersection":
        return "Rejected-pass approved; NYC intersection coordinates via Geoclient; pin verified"
    if fill_method == "park_polygon_correction":
        return "Rejected-pass approved; NYC coordinates with park-interior pin correction; pin verified"
    if intake == "parks_only":
        return "Rejected-pass approved; NYC coordinates and pin URL verified"
    if fill_method == "parks_overlap_key":
        return "Rejected-pass approved; Calendar+Parks title/date match; NYC pin verified"
    if fill_method.startswith("nyc_geosearch"):
        return "Rejected-pass approved; NYC coordinates filled via GeoSearch; pin verified"
    if fill_method == "parent_park_fallback":
        return "Rejected-pass approved; parent park coordinates; pin verified"
    return "Rejected-pass approved; NYC coordinates filled from official reference; pin verified"


def is_canceled_title(title: Any) -> bool:
    return bool(re.search(r"\bCANCEL", str(title or ""), flags=re.IGNORECASE))


def existing_coords_approval_reason(row: dict[str, Any]) -> str:
    intake = row.get("intake_type") or ""
    source = str(row.get("geocoder_source") or "")
    if intake == "parks_only" or "parks" in source:
        return "Supplemental approved; NYC coordinates from Parks feed; pin verified"
    if "calendar" in source:
        return "Supplemental approved; NYC coordinates from calendar intake; pin verified"
    return "Supplemental approved; NYC coordinates from intake source; pin verified"


def canceled_reject_reason(title: str) -> str:
    clean = re.sub(r"<[^>]+>", "", str(title or "")).strip()
    return f"Canceled per Parks feed title ({clean[:120]})."


def run(
    *,
    start_rank: int,
    end_rank: int,
    batch_notes: str,
    dry_run: bool = False,
    allow_live_geosearch: bool = False,
    allow_live_geoclient: bool = False,
) -> int:
    queue_payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(queue_payload, "approval_queue")
    if not queue:
        print(json.dumps({"error": "approval queue empty or missing"}, indent=2))
        return 1

    decisions_payload = load_json_file(DECISIONS_PATH, {})
    if not isinstance(decisions_payload, dict) or not isinstance(decisions_payload.get("decisions"), list):
        print(json.dumps({"error": "decisions file missing decisions array"}, indent=2))
        return 1

    decisions: list[dict[str, Any]] = decisions_payload["decisions"]
    decision_by_rank = {
        int(item["review_rank"]): item
        for item in decisions
        if isinstance(item, dict) and item.get("review_rank") is not None
    }

    gazetteer = ensure_gazetteer()
    parks_overlap = build_parks_overlap_index()
    calendar_parks_overlap = build_calendar_parks_overlap_index()
    parks_properties_index = load_parks_properties_name_index()
    resolver = load_resolver(allow_live_geosearch=allow_live_geosearch)
    geoclient = NYCGeoclientClient.load_default(allow_live=allow_live_geoclient)
    cache_size_before = len(resolver.geosearch_cache)
    geoclient_cache_before = len(geoclient.cache)

    queue_by_rank = {int(row["review_rank"]): row for row in queue if row.get("review_rank") is not None}
    outcomes: list[dict[str, Any]] = []
    approved = 0
    rejected = 0
    skipped = 0
    fill_method_counts: Counter[str] = Counter()

    for rank in range(start_rank, end_rank + 1):
        row = queue_by_rank.get(rank)
        if row is None:
            outcomes.append({"review_rank": rank, "outcome": "missing_row"})
            skipped += 1
            continue

        status = str(row.get("manual_review_status") or "")
        if status not in {"rejected", "pending"}:
            outcomes.append({"review_rank": rank, "outcome": "skipped_not_actionable", "status": status})
            skipped += 1
            continue

        decision = decision_by_rank.get(rank) or {"review_rank": rank}
        reason = str(decision.get("approval_decision_reason") or row.get("approval_decision_reason") or "")

        if status == "rejected" and is_permanent_reject(reason):
            outcomes.append({"review_rank": rank, "outcome": "skipped_permanent_reject", "reason": reason})
            skipped += 1
            continue

        if is_canceled_title(row.get("title")):
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "rejected",
                "approval_decision_reason": canceled_reject_reason(str(row.get("title") or "")),
                "manual_review_notes": batch_notes,
            }
            outcomes.append({"review_rank": rank, "outcome": "rejected_canceled_title"})
            rejected += 1
            continue

        if is_ungeocodable_location(row.get("display_location"), row.get("borough")):
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "rejected",
                "approval_decision_reason": (
                    "Rejected-pass: virtual/online/citywide or otherwise ungeocodable location"
                ),
                "manual_review_notes": batch_notes,
            }
            outcomes.append({"review_rank": rank, "outcome": "rejected_ungeocodable"})
            rejected += 1
            continue

        if status == "pending" and valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "approved",
                "approval_decision_reason": existing_coords_approval_reason(row),
                "manual_review_notes": batch_notes,
            }
            fill_method_counts["existing_intake_coordinates"] += 1
            outcomes.append(
                {
                    "review_rank": rank,
                    "outcome": "approved",
                    "fill_method": "existing_intake_coordinates",
                    "geocoder_source": row.get("geocoder_source"),
                    "proposed_lat": row.get("proposed_lat"),
                    "proposed_lng": row.get("proposed_lng"),
                }
            )
            approved += 1
            continue

        fill = resolve_coordinates(
            row,
            gazetteer,
            parks_overlap,
            resolver,
            calendar_parks_overlap=calendar_parks_overlap,
            geoclient=geoclient,
            parks_properties_index=parks_properties_index,
        )
        if fill:
            queue_by_rank[rank] = patch_queue_row(row, fill)
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "approved",
                "approval_decision_reason": approval_reason(row, fill),
                "manual_review_notes": batch_notes,
            }
            fill_method_counts[str(fill.get("fill_method") or "unknown")] += 1
            outcomes.append(
                {
                    "review_rank": rank,
                    "outcome": "approved",
                    "fill_method": fill["fill_method"],
                    "geocoder_source": fill["geocoder_source"],
                    "proposed_lat": fill["proposed_lat"],
                    "proposed_lng": fill["proposed_lng"],
                    "resolver_tier": fill.get("resolver_tier"),
                    "query_used": fill.get("query_used"),
                }
            )
            approved += 1
        else:
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "rejected",
                "approval_decision_reason": (
                    "Rejected-pass: no resolvable GPS after gazetteer, Geoclient, Parks reference, and GeoSearch fill"
                ),
                "manual_review_notes": batch_notes,
            }
            outcomes.append({"review_rank": rank, "outcome": "rejected_no_fill"})
            rejected += 1

    updated_queue = []
    for row in queue:
        rank = row.get("review_rank")
        if rank is not None and int(rank) in queue_by_rank:
            updated_queue.append(queue_by_rank[int(rank)])
        else:
            updated_queue.append(row)

    updated_decisions = []
    seen: set[int] = set()
    for item in decisions:
        rank = item.get("review_rank")
        if rank is not None and int(rank) in decision_by_rank:
            updated_decisions.append(decision_by_rank[int(rank)])
            seen.add(int(rank))
        else:
            updated_decisions.append(item)
    for rank, item in decision_by_rank.items():
        if start_rank <= rank <= end_rank and rank not in seen:
            updated_decisions.append(item)

    report = {
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_location_resolution_engine",
        "start_rank": start_rank,
        "end_rank": end_rank,
        "batch_notes": batch_notes,
        "approved_count": approved,
        "rejected_count": rejected,
        "skipped_count": skipped,
        "fill_method_counts": dict(fill_method_counts),
        "geosearch_live_calls": resolver._live_calls,
        "geoclient_live_calls": geoclient.live_calls,
        "geosearch_cache_entries_before": cache_size_before,
        "geosearch_cache_entries_after": len(resolver.geosearch_cache),
        "geoclient_cache_entries_before": geoclient_cache_before,
        "geoclient_cache_entries_after": len(geoclient.cache),
        "allow_live_geosearch": allow_live_geosearch,
        "allow_live_geoclient": allow_live_geoclient,
        "parks_properties_index_size": len(parks_properties_index),
        "outcomes": outcomes,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "next_required_step": (
            "Run apply_supplemental_manual_approval_decisions.py, "
            "validate_supplemental_manual_approvals.py, and supplemental tests."
        ),
    }

    if not dry_run:
        save_json_file(
            APPROVAL_QUEUE_PATH,
            {"generated_at_utc": report["generated_at_utc"], "approval_queue": updated_queue},
        )
        decisions_payload["decisions"] = updated_decisions
        save_json_file(DECISIONS_PATH, decisions_payload)
        if allow_live_geosearch and len(resolver.geosearch_cache) > cache_size_before:
            resolver.save_geosearch_cache()
        if allow_live_geoclient and len(geoclient.cache) > geoclient_cache_before:
            geoclient.save_cache()
    save_json_file(FILL_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental location resolution engine pass.")
    parser.add_argument("--start-rank", type=int, required=True)
    parser.add_argument("--end-rank", type=int, required=True)
    parser.add_argument("--batch-notes", required=True, help="manual_review_notes for this rejected pass batch")
    parser.add_argument(
        "--allow-live-geosearch",
        action="store_true",
        help="Allow live NYC Planning GeoSearch API calls (also enabled by NYCIF_ALLOW_LIVE_GEOSEARCH=1).",
    )
    parser.add_argument(
        "--allow-live-geoclient",
        action="store_true",
        help="Allow live NYC Geoclient intersection calls (also enabled by NYCIF_ALLOW_LIVE_GEOCLIENT=1).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.end_rank < args.start_rank:
        print(json.dumps({"error": "end-rank must be >= start-rank"}, indent=2))
        return 1
    allow_live_geosearch = args.allow_live_geosearch or os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    allow_live_geoclient = args.allow_live_geoclient or os.environ.get("NYCIF_ALLOW_LIVE_GEOCLIENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return run(
        start_rank=args.start_rank,
        end_rank=args.end_rank,
        batch_notes=args.batch_notes,
        dry_run=args.dry_run,
        allow_live_geosearch=allow_live_geosearch,
        allow_live_geoclient=allow_live_geoclient,
    )


if __name__ == "__main__":
    sys.exit(main())
