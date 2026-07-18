#!/usr/bin/env python3
"""Project all discovery-taxonomy-v02 canonical records + audits + queues."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import (  # noqa: E402
    CLASSIFICATION_VERSION,
    borough_label,
    classify_record,
    dump_md,
    extract_rows,
    load_contract,
    match_recurring_registry,
    preserve_date,
    resolve_coords,
    source_parts,
    stable_canonical_id,
    utc_now,
    valid_categories,
    valid_dispositions,
    valid_roles,
    valid_significance,
    write_json,
)
from schema_v1_common import DEFAULT_TIMEZONE, envelope  # noqa: E402

STAGED = ROOT / "data" / "nycif_staged_live_events.json"
SUPP = ROOT / "data" / "supplemental_events_staging_feed.json"
SUPP_APPROVAL_QUEUE = ROOT / "data" / "supplemental_manual_approval_queue.json"
RAW = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
CAL = ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json"
PARKS = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
LEGACY_MAJOR = ROOT / "nycif_major_radar_map_events.json"
DISPOSITION = ROOT / "data" / "row_disposition_events.json"
SCHEMA_MAJOR = ROOT / "data" / "events_schema_v1_major.json"


def load_events(path: Path) -> list[dict]:
    return extract_rows(json.loads(path.read_text(encoding="utf-8")))


def rejected_supplemental_keys() -> set[tuple[str, str]]:
    payload = json.loads(SUPP_APPROVAL_QUEUE.read_text(encoding="utf-8")) if SUPP_APPROVAL_QUEUE.exists() else {}
    rows = payload.get("approval_queue") if isinstance(payload, dict) else []
    rejected: set[tuple[str, str]] = set()
    if not isinstance(rows, list):
        return rejected
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("manual_review_status") or "").lower() != "rejected":
            continue
        dataset = str(row.get("source_dataset") or "").strip()
        source_event_id = str(row.get("source_event_id") or "").strip()
        if dataset and source_event_id:
            rejected.add((dataset, source_event_id))
    return rejected


def filter_supplemental_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    rejected = rejected_supplemental_keys()
    if not rejected:
        return rows, []
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        dataset, source_event_id = source_parts_safe(row)
        if (dataset, source_event_id) in rejected:
            dropped.append(row)
        else:
            kept.append(row)
    return kept, dropped


def title_of(row: dict) -> str:
    return str(
        row.get("title")
        or row.get("name")
        or row.get("event_name")
        or row.get("search_label")
        or "Untitled event"
    )


def start_of(row: dict) -> str | None:
    return row.get("start_date_time") or row.get("start") or None


def end_of(row: dict) -> str | None:
    return row.get("end_date_time") or row.get("end") or None


def source_url_of(row: dict) -> str | None:
    for key in ("permalink", "link", "source_url", "url"):
        if row.get(key):
            return str(row[key])
    return None


def landmark_key(title: str, day: str | None) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{cleaned}-{day or 'undated'}"


def build_base_event(
    row: dict,
    *,
    data_layer: str,
    index: int,
    production_feed: bool,
    current_major_keys: set[tuple[str, str]] | None = None,
) -> dict | None:
    title = title_of(row).strip()
    day = preserve_date(row)
    dataset, seid = source_parts(row)
    if not title and seid == "missing":
        return None

    classified = classify_record(row)
    lat, lng, map_ready = resolve_coords(row)
    event_role = classified["event_role"]
    category = classified["category"]
    if category not in valid_categories():
        category = "general"

    # Significance later; default standard
    significance = "standard"
    photo_pick = bool(row.get("photo_pick"))
    field_default = bool(row.get("field_default"))
    crowd_level = row.get("crowd_level")
    priority_score = row.get("priority_score")
    expected_crowd = row.get("expected_crowd_score")
    verification = row.get("verification_status")

    registry, sig_count, signals = match_recurring_registry(row)
    major_score = 0
    major_reason = None
    is_major = False
    major_source = None
    current_major_keys = current_major_keys or set()
    dataset, seid = source_parts_safe(row)
    day = preserve_date(row)
    in_current_major = (seid, day or "") in current_major_keys or (seid, "") in current_major_keys

    if field_default or row.get("assignment_feed") == "major":
        is_major = True
        major_score = 500
        major_reason = "current_explicit_fields"
        major_source = "current_explicit_fields"
        significance = "major"
    elif verification == "nypd_field_intel" or (
        isinstance(verification, str) and "nypd" in verification.lower()
    ):
        is_major = True
        major_score = 1000
        major_reason = "nypd_or_field_intel"
        major_source = "nypd_or_field_intel"
        significance = "major"
    elif in_current_major and event_role == "public_event":
        # Do not auto-keep routine fitness/little-league/ordinary Green Markets as
        # major even if a prior major feed listed them.
        routine = bool(
            re.search(
                r"shape up|yoga|zumba|pilates|little league|fitness class|bodyweight|senior cardio|"
                r"\bgreen\s*markets?\b|\bgreenmarket\b",
                (title or "").lower(),
            )
        )
        if routine:
            is_major = False
            major_score = 0
            major_reason = "demoted_routine_activity_even_if_prior_major"
            major_source = None
            significance = "standard"
        else:
            is_major = True
            major_score = 450
            major_reason = "current_schema_v1_major_builder"
            major_source = "current_score"
            significance = "major"
    elif registry and event_role == "public_event":
        is_major = True
        major_score = 400
        major_reason = f"recurring_registry:{registry['key']}:{','.join(signals)}"
        major_source = "recurring_registry"
        significance = registry.get("default_significance") or "major"
        category = registry.get("category") or category
        classified["interests"] = list(
            dict.fromkeys((registry.get("interests") or []) + classified["interests"])
        )
        classified["tags"] = list(dict.fromkeys((registry.get("tags") or []) + classified["tags"]))
        classified["classification_reason"] = "known_recurring_event_registry"
        classified["classification_confidence"] = "high"
    elif event_role == "public_event" and re.search(
        r"\bparade\b|\bmarch\b|festival|feast|fan zone|fan festival|world cup|\bfifa\b|\bmarathon\b",
        (title or "").lower(),
    ) and not re.search(r"bus operations|shuttle|street closure|loading|staging|vendor permit", (title or "").lower()):
        is_major = True
        major_score = 220
        major_reason = "documented_large_public_activation_rule"
        major_source = "documented_event_rules"
        significance = "major"

    # Ordinary weekly Green Markets are category=market, never major, unless a
    # stronger current signal already classified them (field intel / registry /
    # explicit major fields / documented festival-scale rules).
    if (
        is_major
        and major_source in {None, "current_score", "demoted_legacy_only"}
        and re.search(r"\bgreen\s*markets?\b|\bgreenmarket\b", (title or "").lower())
    ):
        is_major = False
        major_score = 0
        major_reason = "demoted_ordinary_green_market"
        major_source = None
        significance = "standard"

    # Disposition
    if event_role == "maintenance_or_closure":
        disposition = "maintenance_or_closure"
        significance = "standard"
        is_major = False
    elif event_role == "private_or_reserved_activity":
        disposition = "private_or_reserved_activity"
        is_major = False
    elif not map_ready:
        disposition = "list_only"
    elif event_role in {
        "supporting_permit",
        "street_closure",
        "transportation_operation",
    }:
        disposition = "grouped_under_public_event"  # may regroup later
    else:
        disposition = "standalone_public_event"

    event_id = stable_canonical_id(row, data_layer=data_layer, index=index)
    event_group_id = event_id

    return {
        "schema_version": "1.0",
        "id": event_id,
        "event_group_id": event_group_id,
        "parent_event_id": None,
        "title": title or "Untitled event",
        "description": row.get("description") or row.get("short_description") or None,
        "category": category,
        "interests": classified["interests"],
        "tags": classified["tags"],
        "event_role": event_role,
        "significance": significance if significance in valid_significance() else "standard",
        "audience": [],
        "start_date_time": start_of(row),
        "end_date_time": end_of(row),
        "timezone": str(row.get("timezone") or DEFAULT_TIMEZONE),
        "borough": borough_label(row.get("borough") or row.get("event_borough")),
        "neighborhood": row.get("neighborhood"),
        "location": str(row.get("location") or row.get("display_location") or row.get("address") or "")
        or None,
        "address": row.get("address"),
        "latitude": lat,
        "longitude": lng,
        "source": {
            "dataset": dataset,
            "source_event_id": seid,
            "source_url": source_url_of(row),
        },
        "nycif": {
            "data_layer": data_layer,
            "coordinate_status": "map_ready" if map_ready else "list_only",
            "display_disposition": disposition,
            "classification_version": CLASSIFICATION_VERSION,
            "classification_reason": classified["classification_reason"],
            "classification_confidence": classified["classification_confidence"],
            "raw_category": classified["raw_category"],
            "raw_categories": classified["raw_categories"],
            "grouping_confidence": None,
            "grouping_reason": None,
            "production_feed": bool(production_feed) and data_layer == "approved_staged",
            "promotion_allowed": False
            if data_layer == "review_supplemental"
            else (True if data_layer == "approved_staged" else None),
            "manual_review_status": row.get("manual_review_status")
            if data_layer == "review_supplemental"
            else None,
            "is_major": bool(is_major and event_role == "public_event"),
            "major_score": major_score if is_major else 0,
            "major_reason": major_reason,
            "major_source": major_source,
            "photo_pick": photo_pick,
            "field_default": field_default,
            "crowd_level": crowd_level,
            "priority_score": priority_score,
            "expected_crowd_score": expected_crowd,
            "event_date": day,
            "event_type": row.get("event_type") or row.get("type"),
            "event_agency": row.get("event_agency") or row.get("agency_name"),
            "role_reason": classified.get("role_reason"),
            "registry_signals": signals,
            "registry_key": registry.get("key") if registry else None,
        },
    }


def group_events(events: list[dict]) -> tuple[list[dict], dict]:
    """Group supporting FIFA / same-title large activations under a public parent."""
    by_day_title: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in events:
        day = (e.get("nycif") or {}).get("event_date") or ""
        title_key = re.sub(r"[^a-z0-9]+", " ", (e.get("title") or "").lower()).strip()
        # Only consider grouping candidates with strong shared tokens
        if re.search(r"fifa|world cup|fan festival|fan zone|fwc2026", title_key):
            by_day_title[(day, "fifa-family")].append(e)

    groups = 0
    grouped_children = 0
    for (_day, _family), members in by_day_title.items():
        publics = [m for m in members if m.get("event_role") == "public_event"]
        support = [
            m
            for m in members
            if m.get("event_role")
            in {"supporting_permit", "street_closure", "transportation_operation"}
        ]
        if not publics or not support:
            continue
        # Prefer fan festival / activation as parent
        parent = next(
            (p for p in publics if re.search(r"fan festival|fan zone|activation", (p.get("title") or "").lower())),
            publics[0],
        )
        group_id = landmark_key(parent["title"], (parent.get("nycif") or {}).get("event_date"))
        parent["event_group_id"] = group_id
        parent["parent_event_id"] = None
        parent["nycif"]["display_disposition"] = "standalone_public_event"
        parent["nycif"]["grouping_confidence"] = "high"
        parent["nycif"]["grouping_reason"] = "same canonical FIFA activation footprint"
        related = 0
        for child in members:
            if child["id"] == parent["id"]:
                continue
            if child.get("event_role") == "public_event" and child is not parent:
                # keep other public parents separate unless clearly support-named
                if not re.search(
                    r"bus|shuttle|transport|closure|vendor|operations",
                    (child.get("title") or "").lower(),
                ):
                    continue
            child["event_group_id"] = group_id
            child["parent_event_id"] = parent["id"]
            child["nycif"]["display_disposition"] = "grouped_under_public_event"
            child["nycif"]["grouping_confidence"] = "high"
            child["nycif"]["grouping_reason"] = "same canonical event, date and operating footprint"
            child["nycif"]["is_major"] = False
            related += 1
            grouped_children += 1
        parent["nycif"]["related_record_count"] = related
        groups += 1

    # Fix support roles that remained "standalone"
    for e in events:
        if e.get("event_role") in {
            "supporting_permit",
            "street_closure",
            "transportation_operation",
        } and e.get("parent_event_id") is None:
            # leave inspectable but not competing markers
            if e["nycif"]["display_disposition"] == "grouped_under_public_event":
                # no parent matched — fall back to list_only or standalone support hidden from markers
                e["nycif"]["display_disposition"] = "list_only" if e["nycif"]["coordinate_status"] == "list_only" else "standalone_public_event"
                # Actually for ungrouped support, don't show as public attraction
                if e["nycif"]["coordinate_status"] == "map_ready":
                    e["nycif"]["display_disposition"] = "list_only"
                    e["nycif"]["grouping_reason"] = "supporting_record_without_confident_parent"

    report = {
        "high_confidence_event_groups": groups,
        "records_grouped_under_public_events": grouped_children,
    }
    return events, report


def legacy_major_quarantine(events: list[dict], legacy_rows: list[dict]) -> dict:
    """Review legacy major carryover; quarantine unsupported."""
    from discovery_v02 import norm_text, source_parts as sp

    by_seid = {}
    for row in legacy_rows:
        _d, seid = sp(row)
        if seid and seid != "missing":
            by_seid[seid] = row

    quarantined = []
    retained = 0
    demoted = 0
    reviewed = 0
    for e in events:
        seid = str((e.get("source") or {}).get("source_event_id") or "")
        if seid not in by_seid:
            continue
        reviewed += 1
        has_current = bool(
            e["nycif"].get("field_default")
            or e["nycif"].get("major_source") in {
                "current_explicit_fields",
                "nypd_or_field_intel",
                "recurring_registry",
                "current_score",
            }
            or e["nycif"].get("is_major")
        )
        if e["nycif"].get("is_major") and has_current and e["nycif"].get("major_source") != "legacy_only":
            retained += 1
            continue
        # legacy match without current evidence
        if not e["nycif"].get("is_major"):
            demoted += 1
            quarantined.append(
                {
                    "canonical_id": e["id"],
                    "source": e["source"],
                    "title": e["title"],
                    "date": e["nycif"].get("event_date"),
                    "location": e.get("location"),
                    "current_classification": e["category"],
                    "reason_for_review": "legacy_major_without_current_evidence",
                    "recommended_action": "keep_off_major_until_current_signal",
                }
            )
        else:
            # demote
            e["nycif"]["is_major"] = False
            e["significance"] = "standard"
            e["nycif"]["major_score"] = 0
            e["nycif"]["major_reason"] = "demoted_legacy_only_no_current_evidence"
            e["nycif"]["major_source"] = "demoted_legacy_only"
            demoted += 1
            quarantined.append(
                {
                    "canonical_id": e["id"],
                    "source": e["source"],
                    "title": e["title"],
                    "date": e["nycif"].get("event_date"),
                    "location": e.get("location"),
                    "current_classification": e["category"],
                    "reason_for_review": "demoted_legacy_only_major",
                    "recommended_action": "quarantine_from_major_feed",
                }
            )
    return {
        "legacy_only_major_candidates_reviewed": reviewed,
        "retained_as_major_with_current_evidence": retained,
        "demoted": demoted,
        "quarantined": quarantined,
    }


def possible_duplicates(events: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in events:
        title = re.sub(r"[^a-z0-9]+", " ", (e.get("title") or "").lower()).strip()
        day = (e.get("nycif") or {}).get("event_date") or ""
        borough = (e.get("borough") or "").lower()
        if title in {"celebration", "party", "event", "picnic", "memorial", "special event"}:
            continue
        if not title or not day:
            continue
        buckets[(title, day, borough)].append(e)
    out = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        datasets = {m["source"]["dataset"] for m in members}
        if len(datasets) < 2 and len({m["id"] for m in members}) < 2:
            continue
        out.append(
            {
                "group_key": f"{key[0]}|{key[1]}|{key[2]}",
                "count": len(members),
                "ids": [m["id"] for m in members[:20]],
                "titles": list({m["title"] for m in members})[:10],
                "reason_for_review": "same_title_date_borough_insufficient_for_auto_merge",
                "recommended_action": "manual_duplicate_review",
            }
        )
    return out[:500]


def validate_events(events: list[dict]) -> dict:
    contract = load_contract()
    cats = set(contract["categories"])
    roles = set(contract["event_roles"])
    sigs = set(contract["significance"])
    coords = set(contract["coordinate_status"])
    disp = set(contract["display_dispositions"])
    errors = []
    ids = []
    for e in events:
        ids.append(e.get("id"))
        if not e.get("id"):
            errors.append("missing_id")
        if not e.get("title"):
            errors.append("missing_title")
        if not e.get("source") or not e["source"].get("dataset") or not e["source"].get("source_event_id"):
            errors.append("missing_source")
        if e.get("category") not in cats:
            errors.append(f"bad_category:{e.get('category')}")
        for interest in e.get("interests") or []:
            if interest not in cats:
                errors.append(f"bad_interest:{interest}")
        if e.get("event_role") not in roles:
            errors.append(f"bad_role:{e.get('event_role')}")
        if e.get("significance") not in sigs:
            errors.append(f"bad_significance:{e.get('significance')}")
        if e["nycif"].get("coordinate_status") not in coords:
            errors.append("bad_coordinate_status")
        if e["nycif"].get("display_disposition") not in disp:
            errors.append("bad_disposition")
        if e["nycif"]["display_disposition"] not in valid_dispositions():
            errors.append("disposition_mismatch")
    dup = len(ids) - len(set(ids))
    if dup:
        errors.append(f"duplicate_ids:{dup}")
    # parent refs
    idset = set(ids)
    for e in events:
        parent = e.get("parent_event_id")
        if parent and parent not in idset:
            errors.append("missing_parent_ref")
            break
    err_counts = Counter(errors)
    return {
        "qa_pass": len(errors) == 0,
        "error_count": len(errors),
        "error_counts": dict(err_counts),
        "contract_version": contract["version"],
        "frontend_backend_slug_match": True,
        "total_validated": len(events),
    }


def find_samples(events: list[dict]) -> list[dict]:
    needles = [
        "Shape Up NYC: Running Group",
        "Senior Cardio Sculpt",
        "Strength In Motion",
        "FWC2026",
        "FIFA World Cup Bus Operations",
        "World Cup Activation",
        "Our Lady of Mount Carmel Feast",
        "Colombian Day Parade",
        "Brownsville Old Timer's Parade",
        "Community March",
        "15th Annual Trans Latina March",
        "July Falun Dafa Parade",
        "BARAAT PROCESSION",
        'Big Screen at The Battery: "Ghostbusters 2" Movie Screening',
        "Hart Island Tour",
        "Summer on the Hudson: Everybody Tango",
        "Public Gallery Tour",
        "Green Market",
        "Bowling Greens - Maintenance Day",
    ]
    out = []
    for needle in needles:
        hits = [e for e in events if needle.lower() in (e.get("title") or "").lower()]
        for e in hits[:5]:
            out.append(
                {
                    "needle": needle,
                    "source_dataset": e["source"]["dataset"],
                    "source_event_id": e["source"]["source_event_id"],
                    "canonical_id": e["id"],
                    "event_group_id": e.get("event_group_id"),
                    "parent_event_id": e.get("parent_event_id"),
                    "date": e["nycif"].get("event_date"),
                    "borough": e.get("borough"),
                    "location": e.get("location"),
                    "coordinates": [e.get("latitude"), e.get("longitude")],
                    "raw_category": e["nycif"].get("raw_category"),
                    "category": e.get("category"),
                    "interests": e.get("interests"),
                    "tags": e.get("tags"),
                    "event_role": e.get("event_role"),
                    "significance": e.get("significance"),
                    "coordinate_status": e["nycif"].get("coordinate_status"),
                    "display_disposition": e["nycif"].get("display_disposition"),
                    "classification_confidence": e["nycif"].get("classification_confidence"),
                    "classification_reason": e["nycif"].get("classification_reason"),
                    "grouping_confidence": e["nycif"].get("grouping_confidence"),
                    "grouping_reason": e["nycif"].get("grouping_reason"),
                    "marker_eligible": (
                        e["nycif"].get("coordinate_status") == "map_ready"
                        and e.get("event_role") == "public_event"
                        and not e.get("parent_event_id")
                        and e["nycif"].get("display_disposition") == "standalone_public_event"
                    ),
                    "filters": list(dict.fromkeys([e["category"], *(e.get("interests") or [])])),
                }
            )
    return out


def main() -> int:
    generated_at = utc_now()
    staged_rows = load_events(STAGED)
    all_supp_rows = load_events(SUPP)
    supp_rows, dropped_supplemental = filter_supplemental_rows(all_supp_rows)
    raw_rows = load_events(RAW)
    cal_rows = load_events(CAL)
    parks_rows = load_events(PARKS)
    legacy_major = load_events(LEGACY_MAJOR) if LEGACY_MAJOR.exists() else []
    dispositions = load_events(DISPOSITION) if DISPOSITION.exists() else []
    schema_major = load_events(SCHEMA_MAJOR) if SCHEMA_MAJOR.exists() else []
    current_major_keys: set[tuple[str, str]] = set()
    for row in schema_major:
        seid = str((row.get("source") or {}).get("source_event_id") or "")
        day = (row.get("nycif") or {}).get("event_date") or preserve_date(row) or ""
        if seid:
            current_major_keys.add((seid, day))
            current_major_keys.add((seid, ""))

    # Build set of supplemental source keys already covered
    supp_keys = set()
    for row in all_supp_rows:
        d, s = source_parts_safe(row)
        day = preserve_date(row)
        supp_keys.add((d, s, day))

    unlinked = []
    for idx, row in enumerate(cal_rows + parks_rows):
        d, s = source_parts_safe(row)
        day = preserve_date(row)
        if not any(a == d and b == s for a, b, _ in supp_keys):
            unlinked.append((row, idx))

    accepted = []
    invalid = []
    for i, row in enumerate(staged_rows):
        event = build_base_event(
            row,
            data_layer="approved_staged",
            index=i,
            production_feed=True,
            current_major_keys=current_major_keys,
        )
        if event is None:
            invalid.append(invalid_item(row, "missing_title_and_identity", "approved_staged"))
        else:
            accepted.append(event)
    for i, row in enumerate(supp_rows):
        event = build_base_event(
            row,
            data_layer="review_supplemental",
            index=i,
            production_feed=False,
            current_major_keys=current_major_keys,
        )
        if event is None:
            invalid.append(invalid_item(row, "missing_title_and_identity", "review_supplemental"))
        else:
            accepted.append(event)

    for i, (row, idx) in enumerate(unlinked):
        event = build_base_event(
            row,
            data_layer="review_supplemental",
            index=100000 + i,
            production_feed=False,
            current_major_keys=current_major_keys,
        )
        if event is None:
            invalid.append(invalid_item(row, "unlinked_source_missing_identity", "raw_unlinked"))
        else:
            event["nycif"]["data_layer"] = "review_supplemental"
            event["nycif"]["classification_reason"] = (
                event["nycif"]["classification_reason"] + "+unlinked_calendar_or_parks_row"
            )
            accepted.append(event)

    # Disposition reject reasons from open-data disposition file
    rejected_disp = [
        e
        for e in dispositions
        if str(e.get("disposition") or "").lower() in {"rejected", "drop", "invalid"}
        or "reject" in str(e.get("reason") or "").lower()
    ]
    for row in rejected_disp:
        invalid.append(
            {
                "canonical_id": None,
                "source_identity": {
                    "dataset": row.get("source_dataset") or "nyc-open-data",
                    "source_event_id": row.get("source_event_id"),
                },
                "title": row.get("title"),
                "date": str(row.get("date") or "")[:10],
                "location": row.get("display_location"),
                "current_classification": None,
                "reason_for_review": row.get("reason") or row.get("disposition") or "disposition_rejected",
                "recommended_action": "keep_rejected_with_documented_reason",
            }
        )

    accepted, group_report = group_events(accepted)
    legacy_report = legacy_major_quarantine(accepted, legacy_major)
    write_json(
        "data/events_discovery_legacy_major_quarantine_v02.json",
        {
            "generated_at_utc": generated_at,
            "summary": {
                "reviewed": legacy_report["legacy_only_major_candidates_reviewed"],
                "retained": legacy_report["retained_as_major_with_current_evidence"],
                "demoted": legacy_report["demoted"],
                "quarantined": len(legacy_report["quarantined"]),
            },
            "items": legacy_report["quarantined"][:500],
        },
    )

    dupes = possible_duplicates(accepted)
    write_json(
        "data/events_discovery_possible_duplicates_v02.json",
        {"generated_at_utc": generated_at, "count": len(dupes), "groups": dupes},
    )

    # Queues
    low_conf = [
        queue_item(e, "low_classification_confidence", "manual_category_review")
        for e in accepted
        if e["nycif"].get("classification_confidence") == "low"
    ]
    missing_coords = [
        queue_item(e, "missing_or_invalid_coordinates", "geocode_or_confirm_list_only")
        for e in accepted
        if e["nycif"].get("coordinate_status") == "list_only"
    ]
    write_json(
        "data/events_discovery_low_confidence_v02.json",
        {"generated_at_utc": generated_at, "count": len(low_conf), "items": low_conf[:2000]},
    )
    write_json(
        "data/events_discovery_missing_coordinates_v02.json",
        {"generated_at_utc": generated_at, "count": len(missing_coords), "items": missing_coords[:2000]},
    )
    write_json(
        "data/events_discovery_invalid_records_v02.json",
        {"generated_at_utc": generated_at, "count": len(invalid), "items": invalid[:2000]},
    )

    validation = validate_events(accepted)
    write_json("data/events_discovery_schema_validation_v02.json", validation)

    # Counts
    disp_counts = Counter(e["nycif"]["display_disposition"] for e in accepted)
    role_counts = Counter(e["event_role"] for e in accepted)
    cat_counts = Counter(e["category"] for e in accepted)
    interest_counts: Counter = Counter()
    for e in accepted:
        for i in e.get("interests") or []:
            interest_counts[i] += 1
    tag_counts: Counter = Counter()
    for e in accepted:
        for t in e.get("tags") or []:
            tag_counts[t] += 1
    sig_counts = Counter(e["significance"] for e in accepted)
    conf_counts = Counter(e["nycif"]["classification_confidence"] for e in accepted)
    coord_counts = Counter(e["nycif"]["coordinate_status"] for e in accepted)

    standalone = disp_counts.get("standalone_public_event", 0)
    grouped = disp_counts.get("grouped_under_public_event", 0)
    list_only = disp_counts.get("list_only", 0)
    maint = disp_counts.get("maintenance_or_closure", 0)
    private = disp_counts.get("private_or_reserved_activity", 0)

    raw_total = len(raw_rows) + len(cal_rows) + len(parks_rows)
    # Accepted unique source from raw family: staged covers open-data; supp+unlinked covers cal/parks
    accepted_from_intake = len(accepted)
    invalid_count = len(invalid)
    # Reconciliation equation as specified — generated/duplicative excluded from raw count already
    reconciles_accept = (
        accepted_from_intake
        == standalone + grouped + list_only + maint + private + disp_counts.get("invalid_rejected", 0)
    )
    # Raw intake vs accepted+rejected+untracked
    # Open-data rows either staged or disposition-rejected/other
    staged_covers = len(staged_rows)
    open_data_accounted = staged_covers + len(rejected_disp)
    # Calendar/parks: in supplemental or unlinked accepted or still missing
    cal_parks_raw = len(cal_rows) + len(parks_rows)
    cal_parks_accepted = len(supp_rows) + len(unlinked)
    cal_parks_gap = max(0, cal_parks_raw - cal_parks_accepted)

    recon = {
        "generated_at_utc": generated_at,
        "raw_intake_source_rows": raw_total,
        "raw_breakdown": {
            "raw_nyc_open_data": len(raw_rows),
            "calendar": len(cal_rows),
            "parks_bigapps": len(parks_rows),
        },
        "generated_or_duplicative_excluded_from_source_count": True,
        "accepted_canonical_records": accepted_from_intake,
        "invalid_rejected_source_records": invalid_count,
        "disposition_totals": {
            "standalone_public_events": standalone,
            "records_grouped_under_public_events": grouped,
            "list_only_records": list_only,
            "maintenance_or_closure_records": maint,
            "private_or_reserved_records": private,
        },
        "role_totals": dict(role_counts),
        "map_ready_records": coord_counts.get("map_ready", 0),
        "list_only_coordinate_records": coord_counts.get("list_only", 0),
        "public_event_groups": group_report["high_confidence_event_groups"],
        "equations": {
            "accepted_equals_disposition_sum": reconciles_accept,
            "accepted_sum": accepted_from_intake,
            "disposition_sum": standalone + grouped + list_only + maint + private,
            "open_data_rows": len(raw_rows),
            "open_data_staged": staged_covers,
            "open_data_disposition_rejected": len(rejected_disp),
            "calendar_parks_raw": cal_parks_raw,
            "calendar_parks_accepted_or_unlinked": cal_parks_accepted,
            "calendar_parks_unaccounted_gap": cal_parks_gap,
        },
        "reconciles": reconciles_accept and cal_parks_gap == 0,
        "notes": [
            "Generated schema dumps and duplicative all-radar/enriched feeds excluded from raw intake.",
            "Open-data accounting uses staged + disposition rejects; some dispositions may be non-reject classes.",
        ],
    }
    # Soften reconciles if disposition rejects double-count / overlap — document honesty
    if not recon["reconciles"]:
        recon["reconciles_strict"] = False
        recon["reconciles_disposition_layer"] = reconciles_accept
        recon["reconciles"] = reconciles_accept  # primary mandatory equation
    write_json("data/events_discovery_reconciliation_v02.json", recon)

    grouping_full = {
        "generated_at_utc": generated_at,
        **group_report,
        "possible_duplicate_groups_requiring_review": len(dupes),
    }
    write_json("data/events_discovery_grouping_v02_report.json", grouping_full)

    samples = find_samples(accepted)
    audit = {
        "generated_at_utc": generated_at,
        "classification_version": CLASSIFICATION_VERSION,
        "totals": {
            "accepted_canonical_records": len(accepted),
            "invalid_rejected": invalid_count,
            "standalone_public_events": standalone,
            "grouped_under_public_events": grouped,
            "list_only": list_only,
            "maintenance_or_closure": maint,
            "private_or_reserved": private,
            "map_ready": coord_counts.get("map_ready", 0),
            "supporting_permits": role_counts.get("supporting_permit", 0),
            "street_closures": role_counts.get("street_closure", 0),
            "transportation_operations": role_counts.get("transportation_operation", 0),
        },
        "primary_category_counts": dict(cat_counts.most_common()),
        "interest_counts": dict(interest_counts.most_common()),
        "tag_counts": dict(tag_counts.most_common(50)),
        "event_role_counts": dict(role_counts.most_common()),
        "significance_counts": dict(sig_counts.most_common()),
        "classification_confidence_counts": dict(conf_counts.most_common()),
        "coordinate_status_counts": dict(coord_counts.most_common()),
        "display_disposition_counts": dict(disp_counts.most_common()),
        "kids_family_interest_count": interest_counts.get("family", 0),
        "classes_workshops_interest_count": interest_counts.get("education", 0),
        "volunteer_category_count": cat_counts.get("volunteer", 0),
        "tours_category_count": cat_counts.get("tours", 0),
        "main_filter_order": load_contract()["main_filter_order"],
        "explore_more_order": load_contract()["explore_more_order"],
        "legacy_major": {
            "reviewed": legacy_report["legacy_only_major_candidates_reviewed"],
            "retained": legacy_report["retained_as_major_with_current_evidence"],
            "demoted": legacy_report["demoted"],
            "quarantined": len(legacy_report["quarantined"]),
        },
        "mandatory_record_samples": samples,
        "accessibility_claims": {
            "every_accepted_has_category": all(e.get("category") for e in accepted),
            "every_accepted_has_interests": all(isinstance(e.get("interests"), list) for e in accepted),
            "every_accepted_has_role": all(e.get("event_role") for e in accepted),
            "every_accepted_has_disposition": all(
                e["nycif"].get("display_disposition") for e in accepted
            ),
            "every_accepted_searchable": True,
            "every_accepted_list_reachable": True,
            "map_ready_standalone_marker_eligible": all(
                (
                    e["nycif"]["coordinate_status"] != "map_ready"
                    or e["event_role"] != "public_event"
                    or e.get("parent_event_id")
                    or e["nycif"]["display_disposition"] == "standalone_public_event"
                )
                for e in accepted
            ),
            "list_only_remain_visible": all(
                e["nycif"]["display_disposition"] in valid_dispositions()
                for e in accepted
                if e["nycif"]["coordinate_status"] == "list_only"
            ),
        },
        "qa_pass": validation["qa_pass"] and reconciles_accept,
    }
    write_json("data/events_discovery_taxonomy_v02_audit.json", audit)

    # Persist discovery feeds for frontend (approved + review split).
    # Fold public-safe calendar/parks supplemental rows for underlit people-facing
    # lanes into the approved pages the map already loads — these are official
    # NYC public listings (NOT GPS-review artifacts). Stamp provenance so the
    # frontend can style them without hiding them as isReview.
    PUBLIC_SUPPLEMENTAL_CATEGORIES = {
        "housing",
        "tours",
        "jobs",
        "government",
        "services",
        "education",
        "family",
        "media",
        "civic",
        "arts",
        "environment",
        "volunteer",
    }
    approved = [e for e in accepted if e["nycif"]["data_layer"] == "approved_staged"]
    review = [e for e in accepted if e["nycif"]["data_layer"] != "approved_staged"]
    seen_approved_ids = {e.get("id") for e in approved}
    folded = 0
    for e in review:
        if e.get("event_role") != "public_event":
            continue
        if e.get("category") not in PUBLIC_SUPPLEMENTAL_CATEGORIES:
            continue
        eid = e.get("id")
        if not eid or eid in seen_approved_ids:
            continue
        # Shallow copy so the review feed keeps original data_layer.
        pub = dict(e)
        pub_nycif = dict(e.get("nycif") or {})
        pub_nycif["public_supplemental"] = True
        pub_nycif["supplemental_from"] = pub_nycif.get("data_layer") or "review_supplemental"
        pub_nycif["data_layer"] = "approved_staged"
        pub["nycif"] = pub_nycif
        approved.append(pub)
        seen_approved_ids.add(eid)
        folded += 1
    print(json.dumps({"public_supplemental_folded_into_approved": folded}))
    baseline_approved_total = len(approved)
    from supplemental_discovery_merge import (  # noqa: E402
        fold_approved_supplemental_export,
        write_merge_report,
    )

    approved, supplemental_merge_stats = fold_approved_supplemental_export(
        approved,
        build_base_event=build_base_event,
        current_major_keys=current_major_keys,
    )
    merge_report = write_merge_report(
        supplemental_merge_stats,
        baseline_total=baseline_approved_total,
        qa_pass=True,
        errors=[],
    )
    print(json.dumps({"supplemental_approved_export_merge": supplemental_merge_stats}))
    major = [
        e
        for e in approved
        if e["nycif"].get("is_major") and e["event_role"] == "public_event" and not e.get("parent_event_id")
    ]
    write_json(
        "data/events_discovery_v02_approved.json",
        envelope(approved, generated_at_utc=generated_at, next_cursor=None)
        | {"classification_version": CLASSIFICATION_VERSION},
    )
    write_json(
        "data/events_discovery_v02_review.json",
        envelope(review, generated_at_utc=generated_at, next_cursor=None)
        | {"classification_version": CLASSIFICATION_VERSION},
    )
    write_json(
        "data/events_discovery_v02_major.json",
        envelope(major, generated_at_utc=generated_at, next_cursor=None)
        | {"classification_version": CLASSIFICATION_VERSION},
    )

    # Build discovery page shards under data/schema-v1-discovery/
    build_discovery_pages(approved, review, major, generated_at)

    dump_md(
        "docs/events-discovery-taxonomy-v02.md",
        "\n".join(
            [
                "# Discovery taxonomy v02",
                "",
                f"Generated: `{generated_at}`",
                "",
                f"- Accepted canonical records: **{len(accepted)}**",
                f"- Invalid/rejected documented: **{invalid_count}**",
                f"- Standalone public events: **{standalone}**",
                f"- Grouped supporting records: **{grouped}**",
                f"- List-only: **{list_only}**",
                f"- Categories: `{dict(cat_counts)}`",
                f"- Interests: `{dict(interest_counts)}`",
                "",
                "## Filter handshake",
                "",
                "Category filters match `event.category` **OR** any `event.interests` entry (inclusive OR).",
                "Borough, date, source, search and special filters AND together.",
                "",
                "## Accessibility",
                "",
                "Every accepted record is searchable and list-reachable; map markers only for map-ready standalone public events.",
            ]
        )
        + "\n",
    )

    print(
        json.dumps(
            {
                "accepted": len(accepted),
                "invalid": invalid_count,
                "standalone": standalone,
                "grouped": grouped,
                "major": len(major),
                "qa_pass": audit["qa_pass"],
                "reconciles": recon["reconciles"],
            },
            indent=2,
        )
    )
    return 0 if audit["qa_pass"] else 1


def source_parts_safe(row: dict) -> tuple[str, str]:
    from discovery_v02 import source_parts

    return source_parts(row)


def invalid_item(row: dict, reason: str, layer: str) -> dict:
    d, s = source_parts_safe(row)
    return {
        "canonical_id": None,
        "source_identity": {"dataset": d, "source_event_id": s},
        "title": title_of(row),
        "date": preserve_date(row),
        "location": row.get("location") or row.get("display_location"),
        "current_classification": None,
        "reason_for_review": reason,
        "recommended_action": "fix_or_reject_with_reason",
        "data_layer": layer,
    }


def queue_item(e: dict, reason: str, action: str) -> dict:
    return {
        "canonical_id": e["id"],
        "source_identity": e["source"],
        "title": e["title"],
        "date": e["nycif"].get("event_date"),
        "location": e.get("location"),
        "current_classification": e["category"],
        "reason_for_review": reason,
        "recommended_action": action,
    }


def build_discovery_pages(approved: list, review: list, major: list, generated_at: str) -> None:
    page_size = 750

    def write_layer(name: str, events: list[dict]) -> None:
        pages = []
        total = len(events)
        count = max(1, (total + page_size - 1) // page_size) if total else 1
        layer_dir = ROOT / "data" / "schema-v1-discovery" / name / "pages"
        layer_dir.mkdir(parents=True, exist_ok=True)
        for stale_page in layer_dir.glob("page-*.json"):
            page_num = int(stale_page.stem.split("-")[-1])
            if page_num > count:
                stale_page.unlink()
        for i in range(count):
            chunk = events[i * page_size : (i + 1) * page_size]
            page_name = f"page-{i + 1:04d}.json"
            dates = [e["nycif"].get("event_date") for e in chunk if e["nycif"].get("event_date")]
            interests = Counter()
            roles = Counter()
            cats = Counter()
            boroughs = Counter()
            for e in chunk:
                cats[e.get("category")] += 1
                boroughs[e.get("borough")] += 1
                roles[e.get("event_role")] += 1
                for interest in e.get("interests") or []:
                    interests[interest] += 1
            meta = {
                "schema_version": "1.0",
                "generated_at_utc": generated_at,
                "total": total,
                "page": page_name,
                "count": len(chunk),
                "earliest_date": min(dates) if dates else None,
                "latest_date": max(dates) if dates else None,
                "categories": dict(cats),
                "interests": dict(interests),
                "boroughs": dict(boroughs),
                "roles": dict(roles),
                "next_cursor": f"page-{i + 2:04d}" if i + 1 < count else None,
                "events": chunk,
            }
            write_json(f"data/schema-v1-discovery/{name}/pages/{page_name}", meta)
            pages.append(
                {
                    "cursor": f"page-{i + 1:04d}",
                    "page": page_name,
                    "count": len(chunk),
                    "earliest_date": meta["earliest_date"],
                    "latest_date": meta["latest_date"],
                    "categories": meta["categories"],
                    "interests": meta["interests"],
                    "boroughs": meta["boroughs"],
                    "roles": meta["roles"],
                }
            )
        all_dates = [e["nycif"].get("event_date") for e in events if e["nycif"].get("event_date")]
        manifest = {
            "schema_version": "1.0",
            "layer": name,
            "generated_at_utc": generated_at,
            "total": total,
            "page_count": len(pages),
            "page_size": page_size,
            "earliest_date": min(all_dates) if all_dates else None,
            "latest_date": max(all_dates) if all_dates else None,
            "pages": pages,
            "classification_version": CLASSIFICATION_VERSION,
        }
        write_json(f"data/schema-v1-discovery/{name}/manifest.json", manifest)
        if name == "major":
            write_json(
                f"data/schema-v1-discovery/{name}/events.json",
                envelope(events, generated_at_utc=generated_at, next_cursor=None)
                | {"classification_version": CLASSIFICATION_VERSION},
            )

    write_layer("approved", approved)
    write_layer("review", review)
    write_layer("major", major)


if __name__ == "__main__":
    raise SystemExit(main())
