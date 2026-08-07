#!/usr/bin/env python3
"""Compute the "What's New" diff + category coverage over the full city feed.

The frontend already loads the permitted-event discovery pages, so this builder
emits only non-redundant Mission Control artifacts:

1. ``data/nycif_new_events.json`` — occurrence-level arrivals since the prior
   refresh, using OccurrenceIdentityV2 with backward-compatible reads of the old
   day-instance seen index.
2. ``data/comprehensive_feed_report.json`` — category/type and map-eligibility
   coverage over the coordinated staged snapshot.

Map eligibility is semantic. A coordinate merely falling inside the NYC
bounding box is geometry-valid, not an exact public pin. Exact coordinates are
exposed by this artifact only when ``evaluate_map_eligibility`` returns
``MAP_READY``. Legacy rows without evidence remain counted as review/list-only
and keep their evidence-migration state without fabricated provenance.

Safety: reads only staged/derived feeds + its own seen-index. Does not mutate
location_cache.json, GPS/approval artifacts, raw source datasets, or public
publication state.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from occurrence_identity_contract import occurrence_key_v2
from pin_integrity import evaluate_map_eligibility

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGED = DATA / "nycif_staged_live_events.json"

OUT_NEW = DATA / "nycif_new_events.json"
OUT_REPORT = DATA / "comprehensive_feed_report.json"
SEEN_INDEX = DATA / "_event_seen_index.json"

PAST_WINDOW_DAYS = 14

TARGET_CATEGORIES = {
    "sports", "fitness", "parks", "arts", "market", "civic", "government",
    "education", "family", "services", "environment", "volunteer", "jobs",
    "housing", "media", "general",
}

NYC_TYPE_CATEGORY: dict[str, str] = {
    "open culture": "arts",
    "public program/exhibitions": "arts",
    "concert": "arts",
    "single block festival": "arts",
    "street festival": "arts",
    "athletic-charitable": "sports",
    "athletic race / tour": "sports",
    "athletic race/tour": "sports",
    "marathon": "sports",
    "sport - youth": "sports",
    "sport - adult": "sports",
    "farmers market": "market",
    "sidewalk sale": "market",
    "block party": "civic",
    "parade": "civic",
    "play streets": "civic",
    "street event": "civic",
    "open street partner event": "civic",
    "religious event": "civic",
    "rally": "civic",
    "stationary demonstration": "civic",
    "clean-up": "environment",
    "health fair": "services",
    "mobile unit": "services",
    "plaza event": "parks",
    "plaza partner event": "parks",
    "dcas prep/shoot/wrap permit": "media",
    "press conference": "media",
    "production event": "media",
    "red carpet event": "media",
    "rigging permit": "media",
    "shooting permit": "media",
    "theater load in and load outs": "media",
    "special event": "general",
    "miscellaneous": "general",
}


def load_json(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def day_of(value) -> str:
    return str(value or "")[:10]


def category_for(row: dict) -> str:
    etype = str(row.get("event_type") or "").strip().lower()
    if etype in NYC_TYPE_CATEGORY:
        return NYC_TYPE_CATEGORY[etype]
    existing = str(row.get("category") or "").strip().lower()
    return existing or "general"


def evidence_for(row: dict) -> dict | None:
    evidence = row.get("location_evidence")
    if isinstance(evidence, dict):
        return evidence
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    nested = nycif.get("location_evidence")
    if isinstance(nested, dict):
        return nested
    return None


def semantic_location(row: dict, *, lat_key: str, lng_key: str) -> tuple[dict, float | None, float | None]:
    probe = {
        "latitude": row.get(lat_key),
        "longitude": row.get(lng_key),
    }
    evidence = evidence_for(row)
    if evidence is not None:
        probe["location_evidence"] = evidence
    decision = evaluate_map_eligibility(probe)
    if decision["map_eligibility"] != "MAP_READY":
        return decision, None, None
    return (
        decision,
        float(decision.get("normalized_lat", row.get(lat_key))),
        float(decision.get("normalized_lng", row.get(lng_key))),
    )


def occurrence_tracking_keys(row: dict, *, legacy_permit_id: str, start_day: str) -> tuple[str, str]:
    """Return V2 tracking key plus legacy day-instance key for migration reads."""
    dataset, source_event_id, source_start = occurrence_key_v2(row)
    v2_key = f"v2:{dataset}:{source_event_id}@{source_start}"
    legacy_key = f"{legacy_permit_id}@{start_day}"
    return v2_key, legacy_key


def seen_state(
    seen: dict,
    *,
    v2_key: str,
    legacy_key: str,
    generated: str,
    baseline_run: bool,
) -> tuple[bool, str]:
    """Dual-read old/new seen IDs so identity migration cannot flood NEW."""
    previously_seen = v2_key in seen or legacy_key in seen
    first_seen = seen.get(v2_key) or seen.get(legacy_key) or generated
    seen[v2_key] = first_seen
    return (not baseline_run and not previously_seen), first_seen


def event_shell(
    row: dict,
    *,
    event_id: str,
    category: str,
    event_type: str,
    start: str,
    end: str,
    first_seen: str,
    is_new: bool,
    decision: dict,
    latitude: float | None,
    longitude: float | None,
    source_dataset: str,
    source_event_id: str,
) -> dict:
    map_ready = decision["map_eligibility"] == "MAP_READY"
    return {
        "schema_version": "1.1",
        "id": event_id,
        "title": row.get("title") or "NYC event",
        "category": category,
        "event_type": event_type,
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "start_date": start,
        "end_date": end,
        "multi_day": end > start,
        "is_past": end < date.today().isoformat(),
        "first_seen_utc": first_seen,
        "is_new": is_new,
        "timezone": row.get("timezone") or "America/New_York",
        "borough": row.get("borough"),
        "location": row.get("display_location") or row.get("location"),
        "street_closure_type": row.get("street_closure_type"),
        "latitude": latitude if map_ready else None,
        "longitude": longitude if map_ready else None,
        "source": {
            "dataset": source_dataset,
            "source_event_id": source_event_id,
        },
        "nycif": {
            "coordinate_status": "map_ready" if map_ready else "list_only",
            "map_eligibility_state": decision["map_eligibility"],
            "certified_pin": bool(decision["exact_pin_eligible"]),
            "geometry_valid": bool(decision.get("geometry_valid")),
            "location_reason_code": decision.get("reason_code"),
        },
    }


def main() -> int:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    today = date.today()
    floor_day = (today - timedelta(days=PAST_WINDOW_DAYS)).isoformat()

    staged = load_json(STAGED, {})
    rows = staged.get("events") if isinstance(staged, dict) else (staged or [])

    seen = load_json(SEEN_INDEX, {})
    baseline_run = not seen
    events: list[dict] = []
    list_only: list[dict] = []
    by_cat: Counter = Counter()
    by_type: Counter = Counter()
    eligibility_counts: Counter = Counter()
    reason_counts: Counter = Counter()
    new_events: list[dict] = []
    dropped_old = 0
    ambiguous_identity_count = 0

    for r in rows:
        start = day_of(r.get("start_date_time"))
        end = day_of(r.get("end_date_time")) or start
        if not start:
            continue
        if end < floor_day:
            dropped_old += 1
            continue

        permit_id = str(r.get("id") or f"{r.get('source_dataset')}:{r.get('source_event_id')}")
        v2_key, legacy_key = occurrence_tracking_keys(r, legacy_permit_id=permit_id, start_day=start)
        if v2_key.endswith("@identity_ambiguous"):
            ambiguous_identity_count += 1
        is_new, first_seen = seen_state(
            seen,
            v2_key=v2_key,
            legacy_key=legacy_key,
            generated=generated,
            baseline_run=baseline_run,
        )

        etype = r.get("event_type") or "Special Event"
        category = category_for(r)
        decision, latitude, longitude = semantic_location(r, lat_key="lat", lng_key="lng")
        eligibility_counts[decision["map_eligibility"]] += 1
        reason_counts[str(decision.get("reason_code") or "UNKNOWN")] += 1

        event = event_shell(
            r,
            event_id=v2_key,
            category=category,
            event_type=etype,
            start=start,
            end=end,
            first_seen=first_seen,
            is_new=is_new,
            decision=decision,
            latitude=latitude,
            longitude=longitude,
            source_dataset=str(r.get("source_dataset") or "tvpp-9vvx"),
            source_event_id=str(r.get("source_event_id") or ""),
        )
        by_type[etype] += 1
        by_cat[category] += 1
        (events if decision["map_eligibility"] == "MAP_READY" else list_only).append(event)
        if is_new:
            new_events.append({k: event[k] for k in (
                "id", "title", "category", "event_type", "start_date", "end_date", "borough", "first_seen_utc"
            )})

    # Fold the street-festivals projection only when its evidence independently
    # passes the same semantic eligibility authority. Union is still source-ID
    # scoped because this projection represents the same permit family; V2 IDs
    # are used for the seen/new tracker.
    have_ids = {
        e["source"]["source_event_id"]
        for e in events + list_only
        if e["source"]["source_event_id"]
    }
    fest = load_json(DATA / "nycif_street_festivals_feed.json", {})
    for r in (fest.get("events") if isinstance(fest, dict) else []) or []:
        sid = str((r.get("source") or {}).get("source_event_id") or r.get("event_id") or "")
        if not sid or sid in have_ids:
            continue
        start = day_of(r.get("start_date_time")) or str(r.get("start_date") or "")
        end = day_of(r.get("end_date_time")) or str(r.get("end_date") or start)
        if not start or end < floor_day:
            continue

        source_dataset = str((r.get("source") or {}).get("dataset") or "tvpp-9vvx")
        identity_row = dict(r)
        identity_row["source_dataset"] = source_dataset
        identity_row["source_event_id"] = sid
        permit_id = str(r.get("id") or f"{source_dataset}:{sid}")
        v2_key, legacy_key = occurrence_tracking_keys(identity_row, legacy_permit_id=permit_id, start_day=start)
        if v2_key.endswith("@identity_ambiguous"):
            ambiguous_identity_count += 1
        fold_is_new, first_seen = seen_state(
            seen,
            v2_key=v2_key,
            legacy_key=legacy_key,
            generated=generated,
            baseline_run=baseline_run,
        )

        decision, latitude, longitude = semantic_location(r, lat_key="latitude", lng_key="longitude")
        eligibility_counts[decision["map_eligibility"]] += 1
        reason_counts[str(decision.get("reason_code") or "UNKNOWN")] += 1
        category = category_for(r)
        etype = r.get("event_type") or "Street Festival"
        event = event_shell(
            r,
            event_id=v2_key,
            category=category,
            event_type=etype,
            start=start,
            end=end,
            first_seen=first_seen,
            is_new=fold_is_new,
            decision=decision,
            latitude=latitude,
            longitude=longitude,
            source_dataset=source_dataset,
            source_event_id=sid,
        )
        by_type[etype] += 1
        by_cat[category] += 1
        have_ids.add(sid)
        (events if decision["map_eligibility"] == "MAP_READY" else list_only).append(event)
        if fold_is_new:
            new_events.append({k: event[k] for k in (
                "id", "title", "category", "event_type", "start_date", "end_date", "borough", "first_seen_utc"
            )})

    all_events = events + list_only
    save_json(SEEN_INDEX, seen)

    coverage = {
        cat: {
            "count": by_cat.get(cat, 0),
            "event_types": sorted(t for t in by_type if category_for({"event_type": t}) == cat),
        }
        for cat in sorted(set(by_cat) | set(TARGET_CATEGORIES))
    }
    save_json(OUT_NEW, {
        "generated_at_utc": generated,
        "identity_contract": "OccurrenceIdentityV2",
        "new_definition": "canonical v2 occurrence identity absent from previous tracked index",
        "legacy_seen_index_dual_read": True,
        "baseline_run": baseline_run,
        "window": {"past_floor": floor_day, "today": today.isoformat()},
        "total_tracked": len(all_events),
        "new_this_run": len(new_events),
        "identity_ambiguous": ambiguous_identity_count,
        "events": sorted(new_events, key=lambda e: e["start_date"]),
    })
    save_json(OUT_REPORT, {
        "generated_at_utc": generated,
        "source_rows": len(rows),
        "kept": len(all_events),
        "dropped_older_than_window": dropped_old,
        "map_ready": len(events),
        "list_only_or_review": len(list_only),
        "map_eligibility_counts": dict(eligibility_counts),
        "map_eligibility_reason_counts": dict(reason_counts),
        "identity_ambiguous": ambiguous_identity_count,
        "unsupported_exact_pin_promotions": sum(
            1 for event in all_events
            if event["nycif"].get("certified_pin") and event["nycif"].get("map_eligibility_state") != "MAP_READY"
        ),
        "multi_day": sum(1 for e in all_events if e["multi_day"]),
        "past_in_window": sum(1 for e in all_events if e["is_past"]),
        "new_this_run": len(new_events),
        "category_counts": dict(by_cat),
        "event_type_counts": dict(by_type),
        "category_coverage": coverage,
        "qa_pass": len(all_events) > 0 and all(
            not e["nycif"].get("certified_pin") or e["nycif"].get("map_eligibility_state") == "MAP_READY"
            for e in all_events
        ),
    })
    print(json.dumps({
        "source_rows": len(rows),
        "kept": len(all_events),
        "map_ready": len(events),
        "list_only_or_review": len(list_only),
        "identity_ambiguous": ambiguous_identity_count,
        "new_this_run": len(new_events),
        "categories_with_data": len(by_cat),
        "event_types": len(by_type),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
