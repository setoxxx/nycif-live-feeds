#!/usr/bin/env python3
"""Build operator God View digest bookmarking civic people-facing intake status."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, utc_now  # noqa: E402


def main() -> int:
    staging = load_json(DATA_DIR / "civic_people_facing_staging_report.json", {})
    qa = load_json(DATA_DIR / "civic_people_facing_date_time_location_qa.json", {})
    continuity = load_json(DATA_DIR / "civic_people_facing_continuity_report.json", {})
    coverage = load_json(DATA_DIR / "civic_people_facing_map_coverage_report.json", {})
    proposals = load_json(DATA_DIR / "civic_people_facing_geocoding_proposal_report.json", {})
    gap = load_json(DATA_DIR / "civic_food_access_gap_note.json", {})
    sync = load_json(DATA_DIR / "civic_people_facing_sync_summary.json", {})
    status = load_json(ROOT / "status" / "nycif-project-status.json", {})

    digest = {
        "schema_version": "civic-people-facing-godview-v1",
        "generated_at_utc": utc_now(),
        "purpose": "Operator bookmark: where civic people-facing intake stands. Read-only. Not a publish control.",
        "public_map_policy": "Civic rows are Review/Help staging only. Not silent public-map promotion.",
        "checkpoint": {
            "merged_pr": 171,
            "merge_commit": "386e6ef4be3dae654f25f2233939223e9a39dac4",
            "current_phase": status.get("current_phase") or "Civic people-facing coverage / Field Desk push",
            "health": status.get("health"),
            "promotion_allowed": False,
            "phase_2e_authorized": False,
            "m7c_authorized": False,
        },
        "counts": {
            "accepted": staging.get("accepted_count"),
            "quarantined": staging.get("quarantined_count"),
            "events": staging.get("events_count"),
            "opportunities": staging.get("opportunities_count"),
            "help_places": staging.get("help_places_count"),
            "map_ready": (staging.get("coordinate_status_counts") or {}).get("map_ready"),
            "list_only": (staging.get("coordinate_status_counts") or {}).get("list_only"),
            "proposed": (proposals.get("proposed_count")),
            "upcoming_next_7_days": continuity.get("upcoming_next_7_days"),
            "upcoming_next_30_days": continuity.get("upcoming_next_30_days"),
        },
        "by_source": staging.get("by_source") or {},
        "lanes": {
            "Approved": "schema-v1-discovery approved permits (unchanged)",
            "Review": "discovery review (calendar/Parks) UNION schema-v1-civic-review/review",
            "Help Places": "schema-v1-civic-review/help (markets + benefits/SNAP/drop-in/Homebase/aging/NYCHA)",
        },
        "qa": {
            "staging_qa_pass": staging.get("qa_pass"),
            "date_time_location_qa_pass": qa.get("qa_pass"),
            "map_coverage_qa_pass": coverage.get("qa_pass"),
            "every_accepted_row_classified": coverage.get("every_accepted_row_classified"),
            "sync_summary_qa_pass": sync.get("qa_pass"),
        },
        "food_access_gap": {
            "status": gap.get("status"),
            "honesty": gap.get("honesty"),
            "artifact": "data/civic_food_access_gap_note.json",
        },
        "field_desk": {
            "package": "docs/field-desk-map-deploy/civic-people-facing-v01/",
            "preview_after_merge": "?v=civic-people-facing-v01&resetFilters=1&feeds=main",
            "human_push_required": True,
            "bot_cannot_push_field_desk": True,
        },
        "safety": {
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "approved_permit_lane_untouched": True,
        },
        "artifact_links": {
            "staging_feed": "data/civic_people_facing_staging_feed.json",
            "staging_report": "data/civic_people_facing_staging_report.json",
            "date_time_location_qa": "data/civic_people_facing_date_time_location_qa.json",
            "continuity": "data/civic_people_facing_continuity_report.json",
            "map_coverage": "data/civic_people_facing_map_coverage_report.json",
            "geocoding_proposals": "data/civic_people_facing_geocoding_proposals.json",
            "geocoding_proposal_report": "data/civic_people_facing_geocoding_proposal_report.json",
            "food_access_gap": "data/civic_food_access_gap_note.json",
            "civic_review_manifest": "data/schema-v1-civic-review/review/manifest.json",
            "civic_help_manifest": "data/schema-v1-civic-review/help/manifest.json",
            "status": "status/nycif-project-status.json",
            "merged_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/171",
        },
        "next_human_steps": [
            "Push Field Desk civic-people-facing-v01 package (bot cannot push nycif-field-desk)",
            "Smoke: Major+Next7; Review shows calendar/Parks ∪ civic; Help Places directories; Approved unchanged",
            "Do not publish/promote civic pins until explicitly authorized",
            "Soup-kitchen citywide live pin feed remains known gap",
        ],
        "remain_unapproved_unpromoted": [
            "All civic Review/Help rows (promotion_allowed false)",
            "Geocoding proposals pending manual review",
            "Historical Workforce1 / Ready NY / MOIA quarantined for upcoming",
            "Food-access soup-kitchen gap",
            "Phase 2E / location_cache write unauthorized",
        ],
    }
    save_json(DATA_DIR / "civic_people_facing_godview_digest.json", digest)

    # Also inject a compact bookmark into discovery godview digest if present (non-destructive merge).
    discovery = load_json(DATA_DIR / "events_discovery_godview_digest_v02.json", None)
    if isinstance(discovery, dict):
        discovery["civic_people_facing_bookmark"] = {
            "generated_at_utc": digest["generated_at_utc"],
            "merged_pr": 171,
            "accepted": digest["counts"]["accepted"],
            "map_ready": digest["counts"]["map_ready"],
            "list_only": digest["counts"]["list_only"],
            "proposed": digest["counts"]["proposed"],
            "upcoming_next_7_days": digest["counts"]["upcoming_next_7_days"],
            "qa_pass": digest["qa"],
            "digest": "data/civic_people_facing_godview_digest.json",
            "field_desk_preview": digest["field_desk"]["preview_after_merge"],
            "public_map_policy": digest["public_map_policy"],
        }
        save_json(DATA_DIR / "events_discovery_godview_digest_v02.json", discovery)

    print(
        f"godview digest accepted={digest['counts']['accepted']} "
        f"map_ready={digest['counts']['map_ready']} proposed={digest['counts']['proposed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
