#!/usr/bin/env python3
"""Build the canonical evidence-backed permitted-event intake and staging feed.

This keeps the existing source acquisition and matching machinery, but makes
location evidence authoritative before a row can enter the exact-pin staging
feed. Coordinates without validated evidence remain review/list material and are
never promoted merely because they fall inside NYC bounds.

TVPP-style street-segment claims bypass legacy coordinate caches and are
re-resolved through the canonical segment authority before publication. This is
intentional protection against the legacy wrong-block/wrong-borough pin class.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from scripts import build_staged_production_feed as legacy_stage
    from scripts import build_test_enriched_feed as legacy_enrich
    from scripts.legacy_location_evidence_migration import migrate_match
    from scripts.location_evidence_contract import normalize_location_evidence, safe_location_evidence_copy
    from scripts.nyc_location_resolver import parse_street_between
    from scripts.projector_v2_authority import semantic_map_decision
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import build_staged_production_feed as legacy_stage  # type: ignore[no-redef]
    import build_test_enriched_feed as legacy_enrich  # type: ignore[no-redef]
    from legacy_location_evidence_migration import migrate_match
    from location_evidence_contract import normalize_location_evidence, safe_location_evidence_copy
    from nyc_location_resolver import parse_street_between
    from projector_v2_authority import semantic_map_decision


def authoritative_match_for_raw(
    raw: dict[str, Any],
    indexes: dict[str, dict[str, dict[str, Any]]],
    cache: dict[str, dict[str, Any]],
    resolver: Any,
) -> tuple[str, dict[str, Any] | None, str]:
    """Choose location evidence without letting legacy segment coordinates win.

    Street-segment claims are a known legacy wrong-pin class. They go directly
    to the canonical segment resolver. If authoritative segment evidence is not
    available, retain the event without an exact coordinate rather than falling
    back to an old cache/event-id coordinate.
    """
    display = str(raw.get("event_location") or raw.get("location") or "").strip()
    borough = str(raw.get("event_borough") or raw.get("borough") or "").strip()
    if parse_street_between(display):
        segment = resolver._resolve_street_segment(display, borough)  # canonical internal authority
        if segment is not None and segment.resolved:
            return segment.tier, segment.as_match_dict(), "street_segment_authority"
        return "street_segment_unresolved", None, "street_segment_authority"

    match_type, match = legacy_enrich.find_match(raw, indexes, cache, resolver)
    return match_type, match, "legacy_match_stack"


def enrich_with_location_authority(
    raw: dict[str, Any], match_type: str, match: dict[str, Any] | None
) -> dict[str, Any]:
    migrated_match, migration = migrate_match(raw, match_type, match)
    event = legacy_enrich.build_event(raw, match_type, migrated_match)
    evidence = normalize_location_evidence(match_type, migrated_match)
    event["location_evidence"] = evidence
    decision = semantic_map_decision(event)
    event["map_eligibility_state"] = decision["map_eligibility_state"]
    event["coordinate_status"] = decision["coordinate_status"]
    event["certified_pin"] = decision["certified_pin"]
    event["pin_integrity_reason"] = decision["reason_code"]
    event["needs_review"] = decision["map_eligibility_state"] != "MAP_READY"
    event["location_evidence_migration_eligible"] = bool(migration.get("eligible"))
    event["location_evidence_migration_reason"] = migration.get("reason_code")
    event["location_evidence_migration_tier"] = migration.get("tier")
    if decision["map_eligibility_state"] == "MAP_READY":
        event["lat"] = decision["latitude"]
        event["lng"] = decision["longitude"]
    return event


def build_semantic_enriched_feed() -> tuple[dict[str, Any], dict[str, Any]]:
    raw_rows = legacy_enrich.fetch_raw_rows()
    raw_current = [row for row in raw_rows if legacy_enrich.date_key(row.get("start_date_time")) >= legacy_enrich.TODAY_NYC]
    enriched = legacy_enrich.rows_from_payload(legacy_enrich.load_json_file(legacy_enrich.ENRICHED_PATH, []))
    cache = legacy_enrich.location_cache_entries()
    indexes = legacy_enrich.build_indexes(enriched)
    resolver = legacy_enrich.NYCLocationResolver.load_default()

    events: list[dict[str, Any]] = []
    match_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    map_state_counts: dict[str, int] = {}
    migration_reason_counts: dict[str, int] = {}
    migration_tier_counts: dict[str, int] = {}
    certified = 0
    migrated_certified = 0
    segment_authority_certified = 0
    segment_authority_unresolved = 0

    for raw in raw_current:
        match_type, match, route = authoritative_match_for_raw(raw, indexes, cache, resolver)
        match_counts[match_type] = match_counts.get(match_type, 0) + 1
        route_counts[route] = route_counts.get(route, 0) + 1
        event = enrich_with_location_authority(raw, match_type, match)
        state = str(event.get("map_eligibility_state") or "REVIEW_REQUIRED")
        map_state_counts[state] = map_state_counts.get(state, 0) + 1
        certified += int(event.get("certified_pin") is True)
        if route == "street_segment_authority":
            if event.get("certified_pin") is True:
                segment_authority_certified += 1
            else:
                segment_authority_unresolved += 1
        reason = str(event.get("location_evidence_migration_reason") or "UNSPECIFIED")
        migration_reason_counts[reason] = migration_reason_counts.get(reason, 0) + 1
        if event.get("location_evidence_migration_eligible") is True:
            tier = str(event.get("location_evidence_migration_tier") or "UNSPECIFIED")
            migration_tier_counts[tier] = migration_tier_counts.get(tier, 0) + 1
            migrated_certified += int(event.get("certified_pin") is True)
        events.append(event)

    if resolver._live_calls:
        resolver.save_geosearch_cache()
    geoclient_live_calls = int(getattr(getattr(resolver, "geoclient", None), "live_calls", 0) or 0)
    if geoclient_live_calls:
        resolver.geoclient.save_cache()

    events.sort(key=lambda row: (
        row.get("date") or "9999-99-99",
        row.get("start_date_time") or "",
        row.get("borough") or "",
        row.get("title") or "",
    ))
    generated_at = datetime.now(timezone.utc).isoformat()
    feed = {
        "generated_at_utc": generated_at,
        "source_dataset": "tvpp-9vvx",
        "production_feed": False,
        "semantic_location_authority": True,
        "events": events,
    }
    manifest = {
        "generated_at_utc": generated_at,
        "source_dataset": "tvpp-9vvx",
        "today_nyc": legacy_enrich.TODAY_NYC,
        "raw_rows_loaded": len(raw_rows),
        "current_future_rows": len(raw_current),
        "enriched_rows_loaded": len(enriched),
        "location_cache_entries_loaded": len(cache),
        "location_resolver_live_geosearch_calls": resolver._live_calls,
        "location_resolver_live_geoclient_calls": geoclient_live_calls,
        "semantic_feed_events": len(events),
        "certified_map_ready_events": certified,
        "migrated_legacy_matches_certified": migrated_certified,
        "street_segment_authority_certified": segment_authority_certified,
        "street_segment_authority_unresolved": segment_authority_unresolved,
        "map_state_counts": dict(sorted(map_state_counts.items())),
        "match_counts": dict(sorted(match_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "migration_reason_counts": dict(sorted(migration_reason_counts.items())),
        "migration_tier_counts": dict(sorted(migration_tier_counts.items())),
        "coordinates_without_exact_evidence_promoted": 0,
    }
    legacy_enrich.save_json_file(legacy_enrich.TEST_FEED_PATH, feed)
    legacy_enrich.save_json_file(legacy_enrich.MANIFEST_PATH, manifest)
    return feed, manifest


def semantic_staged_event(row: dict[str, Any]) -> dict[str, Any]:
    staged = legacy_stage.staged_event(row)
    staged["location_evidence"] = safe_location_evidence_copy(row.get("location_evidence"))
    staged["map_eligibility_state"] = "MAP_READY"
    staged["coordinate_status"] = "map_ready"
    staged["certified_pin"] = True
    staged["pin_integrity_reason"] = row.get("pin_integrity_reason")
    staged["location_evidence_migration_reason"] = row.get("location_evidence_migration_reason")
    return staged


def build_semantic_staged_feed(feed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = legacy_stage.rows_from_test_feed(feed)
    exact_rows = [
        row for row in rows
        if row.get("map_eligibility_state") == "MAP_READY"
        and row.get("certified_pin") is True
        and row.get("needs_review") is False
        and legacy_stage.valid_lat_lng(row)
    ]
    staged_source_rows, rejected = legacy_stage.apply_one_day_street_dedupe(exact_rows)
    staged_rows = [semantic_staged_event(row) for row in staged_source_rows]
    staged_rows.sort(key=lambda row: (
        row.get("date") or "9999-99-99",
        row.get("start_date_time") or "",
        row.get("borough") or "",
        row.get("title") or "",
    ))
    generated_at = datetime.now(timezone.utc).isoformat()
    staged_feed = {
        "generated_at_utc": generated_at,
        "source": "nycif_live_test_enriched_events.json",
        "production_feed": False,
        "staged_feed": True,
        "production_ready": True,
        "semantic_location_authority": True,
        "events": staged_rows,
    }
    manifest = {
        "generated_at_utc": generated_at,
        "source": "nycif_live_test_enriched_events.json",
        "production_feed": False,
        "staged_feed": True,
        "production_ready": True,
        "semantic_location_authority": True,
        "input_events": len(rows),
        "certified_map_ready_before_dedupe": len(exact_rows),
        "staged_feed_events": len(staged_rows),
        "exact_occurrence_duplicates_suppressed": len(rejected),
        "coordinates_without_exact_evidence_promoted": 0,
        "all_staged_rows_certified": all(
            row.get("certified_pin") is True
            and row.get("map_eligibility_state") == "MAP_READY"
            and isinstance(row.get("location_evidence"), dict)
            and row["location_evidence"].get("exact_pin_eligible") is True
            for row in staged_rows
        ),
    }
    legacy_stage.save_json_file(legacy_stage.STAGED_FEED_PATH, staged_feed)
    legacy_stage.save_json_file(legacy_stage.STAGED_MANIFEST_PATH, manifest)
    return staged_feed, manifest


def main() -> int:
    feed, enriched_manifest = build_semantic_enriched_feed()
    staged, staged_manifest = build_semantic_staged_feed(feed)
    print(json.dumps({
        "enriched": enriched_manifest,
        "staged": staged_manifest,
        "staged_event_count": len(staged.get("events", [])),
    }, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
