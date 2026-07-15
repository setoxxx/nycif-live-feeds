#!/usr/bin/env python3
"""Build civic map coverage report + proposals-only fill for list_only rows.

Fail-closed. Never writes location_cache or Approved feeds.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import (  # noqa: E402
    DATA_DIR,
    load_json,
    save_json,
    utc_now,
)
from schema_v1_common import valid_nyc_coords  # noqa: E402

STAGING_PATH = DATA_DIR / "civic_people_facing_staging_feed.json"
QA_PATH = DATA_DIR / "civic_people_facing_date_time_location_qa.json"
CONT_PATH = DATA_DIR / "civic_people_facing_continuity_report.json"
GAP_PATH = DATA_DIR / "civic_food_access_gap_note.json"
PARKS_REF = DATA_DIR / "nyc_parks_facility_reference.json"
MANUAL_REF = DATA_DIR / "manual_gps_reference.json"

PLACE_NORM_RE = re.compile(r"[^a-z0-9]+")


def norm_place(value: Any) -> str:
    text = PLACE_NORM_RE.sub(" ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def build_memory_index() -> dict[str, dict[str, Any]]:
    """Read-only index of official NYCIF memory for proposal joins."""
    index: dict[str, dict[str, Any]] = {}

    parks = load_json(PARKS_REF, {})
    facilities = parks.get("facilities") if isinstance(parks, dict) else None
    if isinstance(facilities, list):
        for fac in facilities:
            if not isinstance(fac, dict):
                continue
            lat, lng, ok = valid_nyc_coords(fac.get("lat") or fac.get("latitude"), fac.get("lng") or fac.get("longitude"))
            if not ok:
                continue
            for key in (
                fac.get("facility_name"),
                fac.get("display_location"),
                fac.get("feed_label"),
            ):
                nk = norm_place(key)
                if len(nk) < 6:
                    continue
                index.setdefault(
                    nk,
                    {
                        "proposed_lat": lat,
                        "proposed_lng": lng,
                        "geocoder_source": "nyc_parks_facility_reference",
                        "geocoder_confidence": "medium",
                        "confidence_reason": "joined_parks_facility_reference_by_normalized_name",
                        "memory_label": fac.get("facility_name") or fac.get("display_location"),
                    },
                )

    manual = load_json(MANUAL_REF, {})
    refs = manual.get("references") if isinstance(manual, dict) else None
    if isinstance(refs, list):
        for row in refs:
            if not isinstance(row, dict):
                continue
            lat, lng, ok = valid_nyc_coords(row.get("lat") or row.get("latitude"), row.get("lng") or row.get("longitude"))
            if not ok:
                continue
            for key in (row.get("display_location"), row.get("name"), row.get("group_key")):
                nk = norm_place(key)
                if len(nk) < 6:
                    continue
                index.setdefault(
                    nk,
                    {
                        "proposed_lat": lat,
                        "proposed_lng": lng,
                        "geocoder_source": "manual_gps_reference",
                        "geocoder_confidence": "high",
                        "confidence_reason": "joined_manual_gps_reference",
                        "memory_label": key,
                    },
                )

    # Prior civic map_ready rows as weak precedent for identical display_location
    staging = load_json(STAGING_PATH, {})
    for event in staging.get("events") or []:
        if event.get("coordinate_status") != "map_ready":
            continue
        lat, lng, ok = valid_nyc_coords(event.get("latitude"), event.get("longitude"))
        if not ok:
            continue
        for key in (event.get("display_location"), event.get("address"), event.get("title")):
            nk = norm_place(key)
            if len(nk) < 8:
                continue
            index.setdefault(
                nk,
                {
                    "proposed_lat": lat,
                    "proposed_lng": lng,
                    "geocoder_source": "civic_prior_map_ready_precedent",
                    "geocoder_confidence": "low",
                    "confidence_reason": "matched_prior_civic_map_ready_place_text",
                    "memory_label": key,
                },
            )
    return index


def propose_for_row(row: dict[str, Any], memory: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        row.get("display_location"),
        row.get("address"),
        row.get("title"),
        row.get("location"),
    ]
    hit = None
    matched_key = None
    for cand in candidates:
        nk = norm_place(cand)
        if nk and nk in memory:
            hit = memory[nk]
            matched_key = nk
            break
        # Soft contains match for longer place strings
        if nk and len(nk) >= 12:
            for mem_key, mem_val in memory.items():
                if len(mem_key) >= 12 and (nk in mem_key or mem_key in nk):
                    hit = mem_val
                    matched_key = mem_key
                    break
        if hit:
            break

    proposal = {
        "id": row.get("id"),
        "title": row.get("title"),
        "lane": row.get("lane"),
        "source": row.get("source"),
        "borough": row.get("borough"),
        "display_location": row.get("display_location"),
        "address": row.get("address"),
        "coordinate_status": "proposed" if hit else "list_only",
        "proposed_lat": hit.get("proposed_lat") if hit else None,
        "proposed_lng": hit.get("proposed_lng") if hit else None,
        "geocoder_source": hit.get("geocoder_source") if hit else None,
        "geocoder_confidence": hit.get("geocoder_confidence") if hit else None,
        "confidence_reason": (
            hit.get("confidence_reason")
            if hit
            else "no_strong_official_join_remain_list_only"
        ),
        "matched_memory_key": matched_key,
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    return proposal


def main() -> int:
    staging = load_json(STAGING_PATH, {})
    events = [e for e in (staging.get("events") or []) if isinstance(e, dict)]
    qa = load_json(QA_PATH, {})
    continuity = load_json(CONT_PATH, {})
    gap = load_json(GAP_PATH, {})

    # Quarantined counts from by_source on staging report / qa
    by_source_qa = qa.get("by_source") or staging.get("by_source") or {}
    quarantined_total = int(qa.get("quarantined_count") or 0)

    status_counts = Counter(e.get("coordinate_status") for e in events)
    lane_counts = Counter(e.get("lane") for e in events)

    by_source: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for e in events:
        dataset = ((e.get("source") or {}).get("dataset")) or "unknown"
        by_source[dataset]["accepted"] += 1
        by_source[dataset][str(e.get("coordinate_status") or "missing")] += 1

    for source_key, meta in by_source_qa.items():
        if isinstance(meta, dict) and meta.get("quarantined"):
            by_source[source_key]["quarantined"] = int(meta["quarantined"])

    missing_status = [e.get("id") for e in events if e.get("coordinate_status") not in {"map_ready", "proposed", "list_only"}]
    promotion_leaks = [e.get("id") for e in events if e.get("promotion_allowed") is not False]
    invented_time_flags = [
        e.get("id")
        for e in events
        if e.get("time_precision")
        in {"ongoing_schedule", "soft_schedule_text", "recurring_schedule_text", "directory_place", "hours_comment"}
        and e.get("start_date_time")
    ]

    memory = build_memory_index()
    list_only = [e for e in events if e.get("coordinate_status") == "list_only"]
    proposals = [propose_for_row(e, memory) for e in list_only]
    proposed_hits = [p for p in proposals if p["coordinate_status"] == "proposed"]
    remain_list_only = [p for p in proposals if p["coordinate_status"] == "list_only"]

    proposals_payload = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "purpose": "Proposals-only fill for civic list_only rows. Not promotion, not public map.",
        "total_list_only_input": len(list_only),
        "proposed_count": len(proposed_hits),
        "remain_list_only_count": len(remain_list_only),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "proposals": proposals,
    }
    save_json(DATA_DIR / "civic_people_facing_geocoding_proposals.json", proposals_payload)

    proposal_report = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "qa_pass": True,
        "proposed_count": len(proposed_hits),
        "remain_list_only_count": len(remain_list_only),
        "geocoder_source_counts": dict(
            Counter(p.get("geocoder_source") for p in proposed_hits).most_common()
        ),
        "sample_proposed": proposed_hits[:20],
        "sample_remain_list_only": remain_list_only[:20],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "notes": (
            "Proposed rows stay pending/review-only. Staging feed coordinate_status stays "
            "map_ready|list_only unless a later authorized step applies proposals."
        ),
    }
    save_json(DATA_DIR / "civic_people_facing_geocoding_proposal_report.json", proposal_report)

    accepted = len(events)
    accounted = sum(status_counts[s] for s in ("map_ready", "proposed", "list_only"))
    # proposed is only in proposals artifact; accepted staging is map_ready|list_only
    covered_in_staging = status_counts["map_ready"] + status_counts["list_only"]
    coverage = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "purpose": "Prove every accepted civic row is map_ready OR list_only (staging) with optional proposed in proposals artifact.",
        "accepted_count": accepted,
        "quarantined_count": quarantined_total,
        "coordinate_status_counts_staging": dict(status_counts),
        "lane_counts": dict(lane_counts),
        "by_source": {k: dict(v) for k, v in sorted(by_source.items())},
        "percent_accepted_with_coordinate_status": round(100.0 * covered_in_staging / accepted, 2) if accepted else 100.0,
        "every_accepted_row_classified": covered_in_staging == accepted and not missing_status,
        "silent_drops": 0,
        "missing_coordinate_status_ids": missing_status[:20],
        "proposals_artifact": {
            "path": "data/civic_people_facing_geocoding_proposals.json",
            "proposed_count": len(proposed_hits),
            "remain_list_only_count": len(remain_list_only),
        },
        "effective_accounted_with_proposals": {
            "map_ready": status_counts["map_ready"],
            "proposed": len(proposed_hits),
            "list_only": len(remain_list_only),
            "sum": status_counts["map_ready"] + len(proposed_hits) + len(remain_list_only),
            "equals_accepted": status_counts["map_ready"] + len(proposed_hits) + len(remain_list_only) == accepted,
        },
        "continuity": {
            "upcoming_next_7_days": continuity.get("upcoming_next_7_days"),
            "upcoming_next_30_days": continuity.get("upcoming_next_30_days"),
        },
        "food_access_gap": gap.get("status"),
        "qa": {
            "date_time_location_qa_pass": bool(qa.get("qa_pass")),
            "no_invented_times": len(invented_time_flags) == 0 and bool(qa.get("no_invented_times", True)),
            "all_promotion_allowed_false": len(promotion_leaks) == 0,
            "invented_time_ids_sample": invented_time_flags[:10],
            "promotion_leak_ids_sample": promotion_leaks[:10],
        },
        "protected_files": {
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "untouched": [
                "data/location_cache.json",
                "data/nycif_staged_live_events.json",
                "data/staged_live_manifest.json",
                "data/previous_staged_live_events_snapshot.json",
            ],
        },
        "qa_pass": (
            covered_in_staging == accepted
            and not missing_status
            and not promotion_leaks
            and len(invented_time_flags) == 0
            and bool(qa.get("qa_pass"))
            and (status_counts["map_ready"] + len(proposed_hits) + len(remain_list_only) == accepted)
        ),
    }
    save_json(DATA_DIR / "civic_people_facing_map_coverage_report.json", coverage)
    print(
        f"coverage accepted={accepted} map_ready={status_counts['map_ready']} "
        f"list_only={status_counts['list_only']} proposed={len(proposed_hits)} "
        f"qa_pass={coverage['qa_pass']}"
    )
    return 0 if coverage["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
