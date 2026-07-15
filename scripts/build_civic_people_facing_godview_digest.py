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
    photo = load_json(DATA_DIR / "photographer_assignment_calendar_report.json", {})
    photo_full = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    daily = load_json(DATA_DIR / "daily_people_facing_sync_report.json", {})

    digest = {
        "schema_version": "civic-people-facing-godview-v1",
        "generated_at_utc": utc_now(),
        "purpose": "Operator bookmark: civic intake + photographer assignment calendar. Read-only. Not a publish control.",
        "public_map_policy": "Civic rows are Review/Help staging only. Not silent public-map promotion.",
        "checkpoint": {
            "merged_pr": 171,
            "merge_commit": "386e6ef4be3dae654f25f2233939223e9a39dac4",
            "coverage_pr": 172,
            "coverage_merge_commit": "f9df1fd2314b5f921701dc856cc5cb6dd5b1582d",
            "current_phase": status.get("current_phase")
            or "Photographer calendar + daily desk sync",
            "health": status.get("health"),
            "promotion_allowed": False,
            "phase_2e_authorized": False,
            "m7c_authorized": False,
        },
        "daily_pull": {
            "last_success_utc": daily.get("generated_at_utc") if daily.get("qa_pass") else None,
            "last_run_utc": daily.get("generated_at_utc"),
            "qa_pass": daily.get("qa_pass"),
            "report": "data/daily_people_facing_sync_report.json",
            "workflow": ".github/workflows/daily-people-facing-desk-sync.yml",
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
            "photographer_calendar_events": photo.get("total_events"),
            "photographer_days_with_coverage": photo.get("days_with_coverage"),
        },
        "photographer_assignment_calendar": {
            "premium_label": "Photographer Assignment Calendar (premium/operator)",
            "qa_pass": photo.get("qa_pass"),
            "total_events": photo.get("total_events"),
            "days_with_coverage": photo.get("days_with_coverage"),
            "month_counts": photo.get("month_counts"),
            "go_shoot_these": (photo_full.get("go_shoot_these") or [])[:20],
            "artifact": "data/photographer_assignment_calendar_2mo.json",
            "report": "data/photographer_assignment_calendar_report.json",
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
            "photographer_calendar": "data/photographer_assignment_calendar_2mo.json",
            "photographer_calendar_report": "data/photographer_assignment_calendar_report.json",
            "daily_sync_report": "data/daily_people_facing_sync_report.json",
            "status": "status/nycif-project-status.json",
            "merged_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/171",
            "coverage_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/172",
        },
        "next_human_steps": [
            "Push Field Desk civic-people-facing-v01 (+ photographer calendar handshake) to nycif-field-desk Pages",
            "Push admin photographer-calendar-panel + civic God View update",
            "Use Photographer Assignment Calendar for next 2 months of money days",
            "Confirm daily workflow daily-people-facing-desk-sync is enabled",
            "Do not publish/promote to WordPress public map until explicitly authorized",
        ],
        "remain_unapproved_unpromoted": [
            "All civic Review/Help rows (promotion_allowed false)",
            "Geocoding proposals pending manual review",
            "Historical Workforce1 / Ready NY / MOIA quarantined for upcoming",
            "Food-access soup-kitchen gap",
            "Phase 2E / location_cache write unauthorized",
            "Public WordPress map publish unauthorized by this desk package",
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
            "photographer_calendar_events": digest["counts"].get("photographer_calendar_events"),
            "photographer_days_with_coverage": digest["counts"].get("photographer_days_with_coverage"),
            "daily_pull": digest.get("daily_pull"),
            "qa_pass": digest["qa"],
            "digest": "data/civic_people_facing_godview_digest.json",
            "field_desk_preview": digest["field_desk"]["preview_after_merge"],
            "public_map_policy": digest["public_map_policy"],
        }
        discovery["photographer_assignment_bookmark"] = digest["photographer_assignment_calendar"]
        save_json(DATA_DIR / "events_discovery_godview_digest_v02.json", discovery)

    print(
        f"godview digest accepted={digest['counts']['accepted']} "
        f"map_ready={digest['counts']['map_ready']} "
        f"photo_events={digest['counts'].get('photographer_calendar_events')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
