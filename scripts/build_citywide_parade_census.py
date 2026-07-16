#!/usr/bin/env python3
"""Build NYCIF citywide parade / procession / civic-event census (Jul 16–Dec 31, 2026).

Multi-source ingestion (priority order):
  1. NYC Open Data permits (tvpp-9vvx)
  2. Citywide events calendar
  3. NYC Parks BigApps
  4. Historical permits (TBA inference on anchors only)
  5. Editorial anchors
  6. SAPO FOIL operator index (join when present)

Staging/review artifact only — never promotes to public map or location_cache.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, safety_fields, save_json, utc_now  # noqa: E402
import citywide_parade_census_common as census  # noqa: E402

SNAPSHOT_PATH = DATA_DIR / "citywide_parade_census_snapshot.json"
REPORT_PATH = DATA_DIR / "citywide_parade_census_report.json"


def build_census(
    *,
    anchor_registry_path: Path | None = None,
    permit_snapshot_path: Path | None = None,
    calendar_path: Path | None = None,
    parks_path: Path | None = None,
    historical_path: Path | None = None,
    foil_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = census.load_anchor_registry(anchor_registry_path)
    anchors = registry.get("anchors") or []
    permit_rows = census.load_permit_rows(permit_snapshot_path)
    priority_ref = census.load_priority_reference()
    historical_rows = census.load_historical_rows(historical_path)
    foil_index = census.load_foil_operators(foil_path)

    matched_permit_ids: set[str] = set()
    anchor_entries: list[dict[str, Any]] = []
    anchor_match_count = 0

    for anchor in anchors:
        entry = census.census_entry_from_anchor(anchor)
        entry = census.apply_editorial_priority(entry, priority_ref)
        permit_match = census.match_anchor_to_permit(anchor, permit_rows)
        if permit_match:
            entry = census.merge_anchor_with_permit(entry, permit_match, priority_ref=priority_ref)
            pid = str(permit_match.get("source_event_id") or "")
            if pid:
                matched_permit_ids.add(pid)
            anchor_match_count += 1
        anchor_entries.append(entry)

    permit_entries: list[dict[str, Any]] = []
    permit_reject_reasons: Counter[str] = Counter()
    for row in permit_rows:
        ok, reason = census.is_census_candidate(row)
        if not ok:
            permit_reject_reasons[reason] += 1
            continue
        pid = str(row.get("source_event_id") or "")
        if pid and pid in matched_permit_ids:
            continue
        permit_entries.append(
            census.census_entry_from_permit(row, match_reason=reason, priority_ref=priority_ref)
        )

    calendar_entries: list[dict[str, Any]] = []
    calendar_reject_reasons: Counter[str] = Counter()
    if (calendar_path or census.CITYWIDE_CALENDAR_PATH).exists():
        for row in census.load_calendar_rows(calendar_path):
            ok, reason = census.is_calendar_candidate(row)
            if not ok:
                calendar_reject_reasons[reason] += 1
                continue
            calendar_entries.append(
                census.census_entry_from_calendar(row, match_reason=reason, priority_ref=priority_ref)
            )

    parks_entries: list[dict[str, Any]] = []
    parks_reject_reasons: Counter[str] = Counter()
    if (parks_path or census.PARKS_BIGAPPS_PATH).exists():
        for row in census.load_parks_rows(parks_path):
            ok, reason = census.is_parks_candidate(row)
            if not ok:
                parks_reject_reasons[reason] += 1
                continue
            parks_entries.append(
                census.census_entry_from_parks(row, match_reason=reason, priority_ref=priority_ref)
            )

    all_entries = anchor_entries + permit_entries
    all_entries, calendar_added = census.merge_supplemental_entries(all_entries, calendar_entries)
    all_entries, parks_added = census.merge_supplemental_entries(all_entries, parks_entries)

    historical_annotations = census.apply_historical_tba_inference(
        all_entries, historical_rows, anchor_registry=registry
    )
    foil_joins = census.apply_foil_operator_joins(all_entries, foil_index)

    borough_queues = census.group_by_borough(all_entries)
    priority_events = census.priority_queue(all_entries)
    watchlist = census.anchor_watchlist(all_entries)

    confidence_counts = Counter(e.get("confidence") for e in all_entries)
    editorial_priority_counts = Counter(e.get("editorial_priority") for e in all_entries)
    event_kind_counts = Counter(e.get("event_kind") for e in all_entries)
    permit_status_counts = Counter(e.get("permit_status") for e in all_entries)
    source_layer_counts = Counter(e.get("source_layer") for e in all_entries)
    borough_counts = {b: len(rows) for b, rows in borough_queues.items() if rows}

    map_eligible_count = sum(1 for e in all_entries if e.get("map_eligible"))
    calendar_eligible_count = sum(1 for e in all_entries if e.get("calendar_eligible"))

    qa_pass = (
        len(anchors) >= 40
        and all(not e.get("map_eligible") for e in all_entries)
        and map_eligible_count == 0
        and calendar_eligible_count == len(all_entries)
        and all(e.get("confidence") in census.CONFIDENCE_LEVELS for e in all_entries)
        and all(e.get("permit_status") in census.PERMIT_STATUSES for e in all_entries)
    )

    snapshot = {
        "schema_version": "citywide-parade-census-v2",
        "generated_at_utc": utc_now(),
        "window_start": census.WINDOW_START.isoformat(),
        "window_end": census.WINDOW_END.isoformat(),
        "anchor_registry": str(anchor_registry_path or census.ANCHOR_REGISTRY_PATH.relative_to(ROOT)),
        "permit_snapshot": str(permit_snapshot_path or census.PERMIT_SNAPSHOT_PATH.relative_to(ROOT)),
        "source_inputs": {
            "citywide_calendar": str(calendar_path or census.CITYWIDE_CALENDAR_PATH.relative_to(ROOT)),
            "parks_bigapps": str(parks_path or census.PARKS_BIGAPPS_PATH.relative_to(ROOT)),
            "historical_permits": str(historical_path or census.HISTORICAL_PERMITS_PATH.relative_to(ROOT)),
            "sapo_foil_index": str(foil_path or census.SAPO_FOIL_PATH.relative_to(ROOT)),
        },
        "borough_queues": borough_queues,
        "priority_events": priority_events,
        "anchor_watchlist": watchlist,
        "entries": all_entries,
        "counts": {
            "anchor_count": len(anchor_entries),
            "permit_extracted_count": len(permit_entries),
            "calendar_extracted_count": len(calendar_entries),
            "calendar_merged_count": calendar_added,
            "parks_extracted_count": len(parks_entries),
            "parks_merged_count": parks_added,
            "merged_total": len(all_entries),
            "anchor_permit_matches": anchor_match_count,
            "anchor_watchlist_count": len(watchlist),
            "priority_event_count": len(priority_events),
            "historical_tba_annotations": historical_annotations,
            "foil_operator_joins": foil_joins,
            "borough_counts": borough_counts,
            "editorial_priority_counts": dict(editorial_priority_counts),
            "confidence_counts": dict(confidence_counts),
            "event_kind_counts": dict(event_kind_counts),
            "permit_status_counts": dict(permit_status_counts),
            "source_layer_counts": dict(source_layer_counts),
        },
        "notes": (
            "Living census for parades, marches, processions and signature civic events. "
            "Multi-source: permits, citywide calendar, Parks BigApps, editorial anchors. "
            "Historical permits annotate unmatched anchors only (TBA inference). "
            "map_eligible remains false until explicit human promotion."
        ),
        **safety_fields(),
    }

    report = {
        "schema_version": "citywide-parade-census-report-v2",
        "generated_at_utc": snapshot["generated_at_utc"],
        "qa_pass": qa_pass,
        "window_start": snapshot["window_start"],
        "window_end": snapshot["window_end"],
        "anchor_count": len(anchor_entries),
        "permit_extracted_count": len(permit_entries),
        "calendar_extracted_count": len(calendar_entries),
        "calendar_merged_count": calendar_added,
        "parks_extracted_count": len(parks_entries),
        "parks_merged_count": parks_added,
        "merged_total": len(all_entries),
        "anchor_permit_matches": anchor_match_count,
        "anchor_watchlist_count": len(watchlist),
        "priority_event_count": len(priority_events),
        "historical_tba_annotations": historical_annotations,
        "foil_operator_joins": foil_joins,
        "borough_counts": borough_counts,
        "editorial_priority_counts": dict(editorial_priority_counts),
        "confidence_counts": dict(confidence_counts),
        "event_kind_counts": dict(event_kind_counts),
        "permit_status_counts": dict(permit_status_counts),
        "source_layer_counts": dict(source_layer_counts),
        "permit_reject_reasons": dict(permit_reject_reasons),
        "calendar_reject_reasons": dict(calendar_reject_reasons),
        "parks_reject_reasons": dict(parks_reject_reasons),
        "map_eligible_count": map_eligible_count,
        "calendar_eligible_count": calendar_eligible_count,
        "snapshot_path": "data/citywide_parade_census_snapshot.json",
        "anchor_registry_path": "data/nycif_citywide_parade_anchor_registry.json",
        "permit_snapshot_path": "data/raw_nyc_open_data_snapshot.json",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "checks": {
            "all_map_eligible_false": map_eligible_count == 0,
            "anchors_present": len(anchor_entries) >= 40,
            "permit_extraction_ran": True,
            "multi_source_ingestion": True,
            "confidence_values_valid": all(
                e.get("confidence") in census.CONFIDENCE_LEVELS for e in all_entries
            ),
        },
        "next_steps": [
            "Refresh permit snapshot daily via sync_nyc_open_data.py",
            "Re-run build_citywide_parade_census.py after each permit refresh",
            "Expand anchor registry as organizers confirm 2026 dates",
            "Do not set map_eligible=true without explicit promotion authorization",
        ],
    }
    return snapshot, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-registry", default=str(census.ANCHOR_REGISTRY_PATH))
    parser.add_argument("--permit-snapshot", default=str(census.PERMIT_SNAPSHOT_PATH))
    parser.add_argument("--calendar-snapshot", default=str(census.CITYWIDE_CALENDAR_PATH))
    parser.add_argument("--parks-snapshot", default=str(census.PARKS_BIGAPPS_PATH))
    parser.add_argument("--historical-snapshot", default=str(census.HISTORICAL_PERMITS_PATH))
    parser.add_argument("--foil-index", default=str(census.SAPO_FOIL_PATH))
    args = parser.parse_args()

    snapshot, report = build_census(
        anchor_registry_path=Path(args.anchor_registry),
        permit_snapshot_path=Path(args.permit_snapshot),
        calendar_path=Path(args.calendar_snapshot),
        parks_path=Path(args.parks_snapshot),
        historical_path=Path(args.historical_snapshot),
        foil_path=Path(args.foil_index),
    )
    save_json(SNAPSHOT_PATH, snapshot)
    save_json(REPORT_PATH, report)

    print(
        f"citywide parade census qa_pass={report['qa_pass']} "
        f"anchors={report['anchor_count']} permit_extracted={report['permit_extracted_count']} "
        f"calendar_merged={report['calendar_merged_count']} parks_merged={report['parks_merged_count']} "
        f"total={report['merged_total']} anchor_matches={report['anchor_permit_matches']}"
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
