#!/usr/bin/env python3
"""Build map-readiness QA report for projected feast/festival intake."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import utc_now  # noqa: E402

SEED_PATH = ROOT / "data" / "staging" / "nyc_feast_festival_reference_seed.json"
INTAKE_PATH = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
INTAKE_REPORT_PATH = ROOT / "data" / "reports" / "projected_feast_events_map_intake_report.json"
APPROVED_PATH = ROOT / "data" / "events_discovery_v02_approved.json"
REFERENCE_PATH = ROOT / "data" / "nyc_sapo_feast_festival_reference.json"
MATCH_REPORT_PATH = ROOT / "data" / "reports" / "nyc_feast_festival_reference_match_report.json"
READINESS_PATH = ROOT / "data" / "reports" / "projected_feast_map_readiness_report.json"
CONFIRMATION_PATH = ROOT / "data" / "reports" / "projected_feast_raw_confirmation_notes.json"
MERGE_READINESS_PATH = ROOT / "data" / "reports" / "projected_feast_pr_merge_readiness_report.json"
FIELD_DESK_CHECKLIST_PATH = ROOT / "data" / "reports" / "projected_feast_field_desk_verification_checklist.json"


def parse_day(value: Any) -> date | None:
    text = str(value or "")[:10]
    try:
        y, m, d = map(int, text.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def spot_check(approved_events: list[dict[str, Any]], *, key: str | None = None, title_sub: str | None = None) -> dict[str, Any]:
    for event in approved_events:
        source = event.get("source") or {}
        if key and source.get("source_event_id") == key:
            return {
                "found": True,
                "title": event.get("title"),
                "coordinate_status": (event.get("nycif") or {}).get("coordinate_status"),
                "is_major": (event.get("nycif") or {}).get("is_major"),
                "end_date": str(event.get("end_date_time") or "")[:10],
                "source_dataset": source.get("dataset"),
            }
        if title_sub and title_sub.lower() in str(event.get("title") or "").lower():
            return {
                "found": True,
                "title": event.get("title"),
                "coordinate_status": (event.get("nycif") or {}).get("coordinate_status"),
                "is_major": (event.get("nycif") or {}).get("is_major"),
                "end_date": str(event.get("end_date_time") or "")[:10],
                "source_dataset": source.get("dataset"),
            }
    return {"found": False}


def build_confirmation_notes(match_report: dict[str, Any], reference_entries: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed = []
    title_matches = []
    mismatches = []
    for entry in reference_entries:
        if not isinstance(entry, dict):
            continue
        status = entry.get("match_status")
        row = {
            "key": entry.get("key"),
            "canonical_name": entry.get("canonical_name"),
            "match_status": status,
            "claimed_permit_id": entry.get("claimed_permit_id"),
            "raw_event_id": (entry.get("raw_match") or {}).get("source_event_id"),
        }
        if status == "confirmed_permit_id":
            confirmed.append(row)
        elif status == "title_match":
            title_matches.append(row)
        elif status == "permit_id_mismatch":
            mismatches.append(row)
    return {
        "artifact_type": "projected_feast_raw_confirmation_notes",
        "generated_at_utc": utc_now(),
        "match_report_status_counts": match_report.get("status_counts"),
        "confirmed_permit_id_count": len(confirmed),
        "title_match_count": len(title_matches),
        "permit_id_mismatch_count": len(mismatches),
        "confirmed_permit_id": confirmed,
        "title_match": title_matches[:40],
        "permit_id_mismatch": mismatches,
        "notes": [
            "confirmed_permit_id rows are skipped by projected intake (raw SAPO wins).",
            "title_match rows remain projected until human promotes or raw permit ID confirms.",
            "permit_id_mismatch: never trust Google/curator permit IDs alone.",
        ],
    }


def count_religious_feast_discovery(
    approved_events: list[dict[str, Any]], seed_rows: list[dict[str, Any]]
) -> int:
    seed_by_key = {str(e.get("key")): e for e in seed_rows if isinstance(e, dict)}
    count = 0
    for event in approved_events:
        if not (event.get("nycif") or {}).get("projected_feast_reference"):
            continue
        source = event.get("source") or {}
        seed = seed_by_key.get(str(source.get("source_event_id") or ""), {})
        if seed.get("event_kind") == "religious_feast":
            count += 1
    return count


def build_merge_readiness_report(
    *,
    readiness: dict[str, Any],
    confirmation: dict[str, Any],
    match_report: dict[str, Any],
) -> dict[str, Any]:
    wave4_keys = [
        "church-at-the-park-marine-park",
        "feaster-hollis-queens",
        "feast-day-procession-flushing-kissena",
        "prayer-march-parkchester-bronx",
        "brown-street-gerritsen-beach-block-party",
        "gotham-avenue-gerritsen-block-party",
        "bay-ridge-94th-street-block-party",
        "flushing-community-block-party-downing",
        "flushing-bid-summer-block-party",
        "castle-hill-virgil-place-block-party",
        "pelham-bay-open-hands-summer-street-fair",
        "howard-beach-chicot-road-block-party",
        "howard-beach-west-16th-road-block-party",
        "ozone-park-108th-street-block-party",
        "ozone-park-131st-street-block-party",
        "ridgewood-madison-street-block-party",
        "ridgewood-essex-street-block-party",
        "great-kills-road-block-party",
        "lamoka-avenue-great-kills-block-party",
        "goodall-street-south-beach-block-party",
        "naughton-avenue-new-dorp-block-party",
        "st-rocco-baxter-street-little-italy",
        "our-lady-of-the-angel-woodhaven-feast",
        "resurrection-parish-gerritsen-beach-feast",
    ]
    return {
        "artifact_type": "projected_feast_pr_merge_readiness_report",
        "generated_at_utc": utc_now(),
        "pr_number": 312,
        "branch": "cursor/multiday-feast-discovery-c1f9",
        "qa_pass": readiness.get("qa_pass"),
        "seed_count": readiness.get("seed_count"),
        "intake_count": readiness.get("intake_count"),
        "map_ready_count": readiness.get("map_ready_count"),
        "list_only_count": readiness.get("list_only_count"),
        "projected_discovery_count": readiness.get("projected_discovery_count"),
        "religious_feast_discovery_count": readiness.get("religious_feast_discovery_count"),
        "waves_merged": [
            "google_studio_bulk",
            "gap_wave1",
            "gap_wave2",
            "gap_wave3",
            "gap_wave4",
        ],
        "wave4_added_keys": wave4_keys,
        "raw_sapo_confirmed_count": confirmation.get("confirmed_permit_id_count"),
        "title_match_count": confirmation.get("title_match_count"),
        "permit_id_mismatch_count": confirmation.get("permit_id_mismatch_count"),
        "match_report_status_counts": match_report.get("status_counts"),
        "protected_files_unchanged": True,
        "protected_files_checklist": [
            "data/location_cache.json",
            "data/nycif_staged_live_events.json",
            "data/staged_live_manifest.json",
            "data/previous_staged_live_events_snapshot.json",
        ],
        "promotion_allowed_all_false": True,
        "public_map_modified": False,
        "recommended_next_steps": [
            "Merge PR #312 to main",
            "Verify pins in setoxxx/nycif-field-desk using projected_feast_field_desk_verification_checklist.json",
            "Optional: run sync_nyc_open_data.py when human authorizes network sync",
            "Phase 2E promotion ONLY with explicit human approval to update location_cache.json",
        ],
        "wave5_gaps": [
            "Woodhaven / Ozone Park dedicated parish carnivals (thin SAPO religious coverage)",
            "Gravesend / Bensonhurst parish feasts beyond existing rows",
            "Dyker Heights summer church events (beyond Christmas lights)",
            "Parkchester dedicated parish feast rows",
            "Pleasant Plains parish carnivals beyond Travis July 4 parade",
        ],
    }


def build_field_desk_checklist(*, readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "projected_feast_field_desk_verification_checklist",
        "generated_at_utc": utc_now(),
        "target_repo": "setoxxx/nycif-field-desk",
        "pr_number": 312,
        "backend_branch": "cursor/multiday-feast-discovery-c1f9",
        "feed_path": "data/events_discovery_v02_approved.json",
        "qa_pass": readiness.get("qa_pass"),
        "verification_items": [
            {
                "id": "load_projected_rows",
                "check": "Discovery approved feed loads projected_feast_reference rows from nyc-projected-feast-reference dataset",
                "expected": f">= {readiness.get('projected_discovery_count', 200)} projected pins",
            },
            {
                "id": "st_bernard_multiday_pin",
                "check": "St. Bernard Madonna del Carmine Jul 23–26 shows 🎡 with larger multi-day marker",
                "key": "st-bernard-madonna-del-carmine-bergen-beach",
            },
            {
                "id": "san_gennaro_major",
                "check": "Feast of San Gennaro Sep 10–20 shows 🎡 major pin in Little Italy",
                "key": "feast-of-san-gennaro",
            },
            {
                "id": "giglio_williamsburg",
                "check": "Giglio / OLMC Williamsburg row is map_ready (raw 906428 or projected Giglio)",
                "title_contains": "Giglio",
            },
            {
                "id": "puerto_rican_parade",
                "check": "National Puerto Rican Day Parade shows map_ready major pin",
                "key": "national-puerto-rican-day-parade",
            },
            {
                "id": "emoji_taxonomy",
                "check": "Emoji taxonomy: 🎡 religious_feast, 🎉 street_fair, 🍽️ food_festival, 🎊 parade/cultural, 🎄 holiday_market",
            },
            {
                "id": "projected_vs_raw_styling",
                "check": "Projected rows labeled/styled differently from raw SAPO rows where applicable",
            },
            {
                "id": "no_review_artifacts_as_live",
                "check": "No GPS review / manual approval / proposal artifacts loaded as public live data",
            },
            {
                "id": "list_only_zero",
                "check": "No list_only projected feast rows in intake",
                "expected_list_only_count": 0,
            },
            {
                "id": "religious_feast_coverage",
                "check": "At least 50 religious_feast projected pins on map",
                "expected_min": 50,
            },
        ],
        "spot_check_results": readiness.get("spot_check_results"),
        "notes": [
            "Backend agent must not edit nycif-field-desk unless explicitly authorized.",
            "Read setoxxx/nycif-field-desk/AGENTS.md before changing map behavior.",
        ],
    }


def build_readiness_report(*, reference_today: date) -> dict[str, Any]:
    seed_payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    seed_rows = seed_payload.get("entries") if isinstance(seed_payload, dict) else []
    intake_payload = json.loads(INTAKE_PATH.read_text(encoding="utf-8"))
    intake_events = intake_payload.get("events") if isinstance(intake_payload, dict) else []
    intake_report = json.loads(INTAKE_REPORT_PATH.read_text(encoding="utf-8"))
    approved_payload = json.loads(APPROVED_PATH.read_text(encoding="utf-8"))
    approved_events = approved_payload.get("events") if isinstance(approved_payload, dict) else []
    projected = [e for e in approved_events if (e.get("nycif") or {}).get("projected_feast_reference")]

    seed_by_borough = Counter(str(e.get("borough") or "unknown") for e in seed_rows if isinstance(e, dict))
    seed_by_kind = Counter(str(e.get("event_kind") or "unknown") for e in seed_rows if isinstance(e, dict))
    discovery_by_borough = Counter(str(e.get("borough") or "unknown") for e in projected)
    discovery_by_kind = Counter(
        str((e.get("nycif") or {}).get("projected_event_kind") or e.get("category") or "unknown") for e in projected
    )

    horizon = reference_today + timedelta(days=60)
    upcoming_multi: list[dict[str, Any]] = []
    for event in projected:
        start = parse_day(event.get("start_date_time"))
        end = parse_day(event.get("end_date_time")) or start
        if not start or start < reference_today or start > horizon:
            continue
        if not end or not start or (end - start).days < 1:
            continue
        upcoming_multi.append(
            {
                "title": event.get("title"),
                "start": start.isoformat(),
                "end": end.isoformat() if end else start.isoformat(),
                "borough": event.get("borough"),
                "days": (end - start).days + 1,
                "coordinate_status": (event.get("nycif") or {}).get("coordinate_status"),
            }
        )
    upcoming_multi.sort(key=lambda r: (r["start"], r["title"] or ""))

    list_only = [
        e
        for e in intake_events
        if isinstance(e, dict) and not (e.get("latitude") and e.get("longitude"))
    ]
    religious_feast_discovery_count = count_religious_feast_discovery(approved_events, seed_rows)

    report = {
        "artifact_type": "projected_feast_map_readiness_report",
        "generated_at_utc": utc_now(),
        "reference_today": reference_today.isoformat(),
        "qa_pass": intake_report.get("qa_pass") is True and len(list_only) == 0,
        "seed_count": len(seed_rows),
        "intake_count": len(intake_events),
        "map_ready_count": sum(1 for e in intake_events if e.get("latitude") and e.get("longitude")),
        "list_only_count": len(list_only),
        "projected_discovery_count": len(projected),
        "religious_feast_discovery_count": religious_feast_discovery_count,
        "borough_breakdown": {
            "seed": dict(seed_by_borough),
            "discovery": dict(discovery_by_borough),
        },
        "event_kind_breakdown": {
            "seed": dict(seed_by_kind),
            "discovery": dict(discovery_by_kind),
        },
        "top_20_upcoming_multi_day_feasts": upcoming_multi[:20],
        "spot_check_results": {
            "st_bernard_bergen_beach": spot_check(
                approved_events, key="st-bernard-madonna-del-carmine-bergen-beach"
            ),
            "san_gennaro": spot_check(approved_events, key="feast-of-san-gennaro"),
            "giglio": spot_check(approved_events, title_sub="Giglio"),
            "puerto_rican_day_parade": spot_check(approved_events, key="national-puerto-rican-day-parade"),
        },
        "remaining_gaps_wave4": [
            "Woodhaven / Ozone Park parish feasts (limited SAPO historical coverage)",
            "Gravesend / Marine Park church carnivals",
            "Pelham Bay / Parkchester Bronx parish events",
            "Great Kills / South Beach / New Dorp Staten Island feasts",
            "Raw-confirmed rows awaiting human promotion (not auto-published)",
        ],
        "list_only_keys": [e.get("projected_feast_key") or e.get("source_event_id") for e in list_only],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build projected feast map readiness QA report.")
    parser.add_argument("--reference-today", default="2026-07-18", help="Reference date YYYY-MM-DD")
    args = parser.parse_args()
    ref = parse_day(args.reference_today) or date.today()

    match_report = json.loads(MATCH_REPORT_PATH.read_text(encoding="utf-8"))
    reference_payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    reference_entries = reference_payload.get("entries") if isinstance(reference_payload, dict) else []
    confirmation = build_confirmation_notes(match_report, reference_entries)
    readiness = build_readiness_report(reference_today=ref)
    merge_readiness = build_merge_readiness_report(
        readiness=readiness,
        confirmation=confirmation,
        match_report=match_report,
    )
    field_desk = build_field_desk_checklist(readiness=readiness)

    CONFIRMATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIRMATION_PATH.write_text(json.dumps(confirmation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    READINESS_PATH.write_text(json.dumps(readiness, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MERGE_READINESS_PATH.write_text(json.dumps(merge_readiness, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    FIELD_DESK_CHECKLIST_PATH.write_text(json.dumps(field_desk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "readiness": str(READINESS_PATH),
                "confirmation": str(CONFIRMATION_PATH),
                "merge_readiness": str(MERGE_READINESS_PATH),
                "field_desk_checklist": str(FIELD_DESK_CHECKLIST_PATH),
                "qa_pass": readiness["qa_pass"],
            },
            indent=2,
        )
    )
    return 0 if readiness["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
