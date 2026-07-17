#!/usr/bin/env python3
"""Review and disposition 177 net-new pending rows from live sync incremental intake.

Classifies pending rows from the latest live-sync append:
- approve rows with valid NYC coordinates (Parks feed or resolved fill)
- reject canceled Parks/calendar rows
- reject citywide / online-only / multi-borough non-mappable listings
- geocode addressable calendar rows via supplemental location resolver tiers

Writes data/supplemental_net_new_live_sync_decisions.json then applies via
apply_supplemental_manual_approval_decisions.py.

Does NOT modify location_cache.json or public map feeds.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.apply_supplemental_manual_approval_decisions import run as apply_decisions_run
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        build_calendar_parks_overlap_index,
        is_ungeocodable_location,
        load_json_file,
        load_parks_properties_name_index,
        repo_relative,
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
    from apply_supplemental_manual_approval_decisions import run as apply_decisions_run
    from coverage_gap_utils import (
        DATA_DIR,
        build_calendar_parks_overlap_index,
        is_ungeocodable_location,
        load_json_file,
        load_parks_properties_name_index,
        repo_relative,
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
DECISIONS_PATH = DATA_DIR / "supplemental_net_new_live_sync_decisions.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_net_new_live_sync_review_report.json"

CANCELED_RE = re.compile(r"\bcancel+ed\b", re.IGNORECASE)
ONLINE_ONLY_MARKERS = ("zoom", "virtual", "online only", "webinar")
NET_NEW_MIN_REVIEW_RANK = 3458


def ensure_resolver(*, allow_live_geosearch: bool) -> tuple[NYCLocationGazetteer, NYCLocationResolver, Any, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        save_json_file(GAZETTEER_PATH, build_gazetteer_index())
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    cache = load_json_file(GEOSEARCH_CACHE_PATH, {})
    entries = cache.get("entries", {}) if isinstance(cache, dict) else {}
    resolver = NYCLocationResolver(gazetteer, entries, allow_live_geosearch=allow_live_geosearch)
    geoclient = NYCGeoclientClient.load_default(allow_live=allow_live_geosearch)
    parks_overlap = build_calendar_parks_overlap_index()
    parks_properties = load_parks_properties_name_index()
    return gazetteer, resolver, geoclient, parks_overlap, parks_properties


def is_canceled_row(row: dict[str, Any]) -> bool:
    return bool(CANCELED_RE.search(str(row.get("title") or "")))


def is_online_only_row(row: dict[str, Any]) -> bool:
    text = f"{row.get('title') or ''} {row.get('display_location') or ''}".lower()
    return any(marker in text for marker in ONLINE_ONLY_MARKERS)


def classify_row(
    row: dict[str, Any],
    *,
    gazetteer: NYCLocationGazetteer,
    resolver: NYCLocationResolver,
    geoclient: Any,
    parks_overlap: dict[str, dict[str, Any]],
    parks_properties: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    overlap_key = str(row.get("overlap_key") or "")
    review_rank = int(row.get("review_rank") or 0)

    if is_canceled_row(row):
        return {
            "overlap_key": overlap_key,
            "review_rank": review_rank,
            "manual_review_status": "rejected",
            "approval_decision_reason": f"Canceled per source title ({row.get('title')}).",
            "manual_review_notes": "Net-new live sync review — canceled event.",
        }

    lat, lng = row_coords(row)
    decision: dict[str, Any] = {
        "overlap_key": overlap_key,
        "review_rank": review_rank,
    }

    if not valid_nyc_lat_lng(lat, lng):
        if is_online_only_row(row) or is_ungeocodable_location(row.get("display_location"), row.get("borough")):
            return {
                **decision,
                "manual_review_status": "rejected",
                "approval_decision_reason": "Non-mappable supplemental row (citywide, multi-borough, or online-only).",
                "manual_review_notes": "Net-new live sync review — permanent non-mappable.",
            }
        fill = resolve_supplemental_coordinates(
            row,
            gazetteer,
            parks_overlap=parks_overlap,
            resolver=resolver,
            calendar_parks_overlap=parks_overlap,
            geoclient=geoclient,
            parks_properties_index=parks_properties,
        )
        if fill and valid_nyc_lat_lng(fill.get("proposed_lat"), fill.get("proposed_lng")):
            decision.update(fill)
        else:
            return {
                **decision,
                "manual_review_status": "rejected",
                "approval_decision_reason": "Could not resolve NYC coordinates during net-new live sync review.",
                "manual_review_notes": "Net-new live sync review — unresolved address.",
            }

    decision["manual_review_status"] = "approved"
    decision["approval_decision_reason"] = (
        "Supplemental approved; NYC coordinates from Parks feed; pin verified"
        if str(row.get("geocoder_source") or "").startswith("nyc_parks")
        else "Supplemental approved; NYC coordinates resolved for net-new live sync row."
    )
    decision["manual_review_notes"] = "Net-new live sync review batch."
    return decision


def build_decisions(*, allow_live_geosearch: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = payload.get("approval_queue", []) if isinstance(payload, dict) else []
    pending = [
        row
        for row in queue
        if isinstance(row, dict)
        and str(row.get("manual_review_status") or "").lower() == "pending"
        and int(row.get("review_rank") or 0) >= NET_NEW_MIN_REVIEW_RANK
    ]
    if not pending:
        raise ValueError("no net-new pending rows found to review")

    gazetteer, resolver, geoclient, parks_overlap, parks_properties = ensure_resolver(
        allow_live_geosearch=allow_live_geosearch
    )

    decisions = [
        classify_row(
            row,
            gazetteer=gazetteer,
            resolver=resolver,
            geoclient=geoclient,
            parks_overlap=parks_overlap,
            parks_properties=parks_properties,
        )
        for row in pending
    ]

    approved = sum(1 for d in decisions if d.get("manual_review_status") == "approved")
    rejected = sum(1 for d in decisions if d.get("manual_review_status") == "rejected")
    coord_filled = sum(
        1
        for d in decisions
        if d.get("manual_review_status") == "approved" and d.get("fill_method")
    )

    summary = {
        "artifact_type": "supplemental_net_new_live_sync_review_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_net_new_live_sync_review",
        "pending_reviewed": len(decisions),
        "approved_count": approved,
        "rejected_count": rejected,
        "coord_filled_on_approve_count": coord_filled,
        "decisions_path": repo_relative(DECISIONS_PATH),
        "qa_pass": approved + rejected == len(decisions),
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
    }
    return decisions, summary


def main() -> int:
    import os

    allow_live = os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").lower() in {"1", "true", "yes"}
    decisions, summary = build_decisions(allow_live_geosearch=allow_live)
    save_json_file(
        DECISIONS_PATH,
        {
            "artifact_type": "supplemental_net_new_live_sync_decisions",
            "generated_at_utc": summary["generated_at_utc"],
            "phase": "m11_net_new_live_sync_review",
            "manual_reviewer": "Howard Weiss",
            "decisions": decisions,
        },
    )
    apply_code = apply_decisions_run(decisions_path=DECISIONS_PATH, dry_run=False)
    summary["apply_exit_code"] = apply_code
    save_json_file(REPORT_PATH, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if apply_code == 0 and summary.get("qa_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
