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
    quality = load_json(DATA_DIR / "photographer_money_day_quality_report.json", {})
    packs = load_json(DATA_DIR / "photographer_money_day_pack_report.json", {})
    pack_tom = load_json(DATA_DIR / "photographer_money_day_pack_tomorrow.json", {})
    viral = load_json(DATA_DIR / "photographer_viral_recurrence_report.json", {})
    viral_pack = load_json(DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json", {})
    daily = load_json(DATA_DIR / "daily_people_facing_sync_report.json", {})

    digest = {
        "schema_version": "civic-people-facing-godview-v1",
        "generated_at_utc": utc_now(),
        "purpose": "Operator bookmark: civic intake + photographer Money-Day Desk v2. Read-only. Not a publish control.",
        "public_map_policy": "Civic rows are Review/Help staging only. Not silent public-map promotion.",
        "checkpoint": {
            "merged_pr": 171,
            "merge_commit": "386e6ef4be3dae654f25f2233939223e9a39dac4",
            "coverage_pr": 172,
            "coverage_merge_commit": "f9df1fd2314b5f921701dc856cc5cb6dd5b1582d",
            "photographer_calendar_pr": 173,
            "current_phase": status.get("current_phase")
            or "Photographer Money-Day Desk v2",
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
            "money_day_today": (packs.get("today") or {}).get("total_events"),
            "money_day_tomorrow": (packs.get("tomorrow") or {}).get("total_events"),
            "viral_recurrence_matches": viral.get("match_count"),
            "viral_returning_likely": (viral.get("label_counts") or {}).get("returning_likely"),
            "viral_next_14d_magnets": viral.get("next_14d_crowd_magnets"),
        },
        "photographer_assignment_calendar": {
            "premium_label": "Photographer Assignment Calendar (premium/operator) — Money-Day Desk v2",
            "qa_pass": photo.get("qa_pass"),
            "total_events": photo.get("total_events"),
            "days_with_coverage": photo.get("days_with_coverage"),
            "month_counts": photo.get("month_counts"),
            "coordinate_status_counts": photo.get("coordinate_status_counts"),
            "quality": {
                "qa_pass": quality.get("qa_pass"),
                "events_removed_vs_baseline": (quality.get("delta_vs_baseline") or {}).get("events_removed"),
                "top_exclude_reasons": quality.get("top_exclude_reasons"),
                "report": "data/photographer_money_day_quality_report.json",
            },
            "today_pack": packs.get("today"),
            "tomorrow_pack": packs.get("tomorrow"),
            "tomorrow_top_go_shoot": (pack_tom.get("go_shoot") or [])[:10],
            "go_shoot_these": (photo_full.get("go_shoot_these") or [])[:20],
            "viral_recurrence": {
                "qa_pass": viral.get("qa_pass"),
                "match_count": viral.get("match_count"),
                "label_counts": viral.get("label_counts"),
                "next_14d_crowd_magnets": viral.get("next_14d_crowd_magnets"),
                "top_returning_examples": viral.get("top_returning_examples"),
                "next_14d_top": (viral_pack.get("crowd_magnets") or [])[:10],
                "foil_operator_joins": viral.get("foil_operator_joins"),
                "artifact": "data/photographer_viral_recurrence_matches.json",
                "pack": "data/photographer_viral_recurrence_pack_next_14d.json",
                "foil_index": "data/sapo_foil_operator_index.json",
            },
            "artifact": "data/photographer_assignment_calendar_2mo.json",
            "report": "data/photographer_assignment_calendar_report.json",
            "pack_today": "data/photographer_money_day_pack_today.json",
            "pack_tomorrow": "data/photographer_money_day_pack_tomorrow.json",
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
            "assignment_mode_preview": "?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=YYYY-MM-DD&assignment=1",
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
            "money_day_quality": "data/photographer_money_day_quality_report.json",
            "money_day_pack_today": "data/photographer_money_day_pack_today.json",
            "money_day_pack_tomorrow": "data/photographer_money_day_pack_tomorrow.json",
            "viral_recurrence_matches": "data/photographer_viral_recurrence_matches.json",
            "viral_recurrence_pack": "data/photographer_viral_recurrence_pack_next_14d.json",
            "historical_permits": "data/nyc_permits_historical_snapshot.json",
            "sapo_foil_operator_index": "data/sapo_foil_operator_index.json",
            "daily_sync_report": "data/daily_people_facing_sync_report.json",
            "status": "status/nycif-project-status.json",
            "merged_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/171",
            "coverage_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/172",
            "photographer_calendar_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/173",
            "money_day_v2_pr": "https://github.com/setoxxx/nycif-live-feeds/pull/174",
        },
        "next_human_steps": [
            "Push Field Desk civic-people-facing-v01 (+ assignment=1 app JS) to nycif-field-desk Pages",
            "Push admin photographer-calendar-panel with Returning from last year section",
            "Shoot from Today/Tomorrow packs + viral recurrence next-14d magnets",
            "File FOIL for SAPO/CECM full application PDFs; fill data/sapo_foil_operator_index.json",
            "Confirm daily workflow daily-people-facing-desk-sync is enabled",
            "Do not publish/promote to WordPress public map until explicitly authorized",
        ],
        "remain_unapproved_unpromoted": [
            "All civic Review/Help rows (promotion_allowed false)",
            "Geocoding proposals pending manual review",
            "Historical Workforce1 / Ready NY / MOIA quarantined for upcoming",
            "Food-access soup-kitchen gap",
            "FOIL applicant/org identity not yet filled (sapo_foil_operator_index empty)",
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
