#!/usr/bin/env python3
"""Classify unresolved public-event location work without promoting coordinates.

This report-only lane inventories Projector V3 public occurrences whose location
state is LIST_ONLY or REVIEW_REQUIRED. It assigns exactly one deterministic
resolver bucket and a next resolver step. It never changes canonical events,
location_cache.json, map eligibility, certified_pin, or public feed artifacts.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
OUT = ROOT / "data" / "unresolved_location_backlog_v1.json"
REPORT = ROOT / "data" / "unresolved_location_backlog_v1_report.json"

BUCKETS = (
    "KNOWN_FACILITY",
    "KNOWN_VENUE",
    "CEMSID",
    "EXACT_ADDRESS",
    "INTERSECTION",
    "PARK_SUBFACILITY",
    "SPORTS_FIELD",
    "ROUTE_OR_STREET_SEGMENT",
    "BOROUGH_ONLY",
    "MALFORMED_SOURCE",
)
NEXT_STEP = {
    "KNOWN_FACILITY": "resolve_approved_facility_registry",
    "KNOWN_VENUE": "resolve_approved_venue_registry",
    "CEMSID": "resolve_cemsid_registry",
    "EXACT_ADDRESS": "canonical_address_then_geocoder_review",
    "INTERSECTION": "canonical_intersection_then_geocoder_review",
    "PARK_SUBFACILITY": "resolve_nyc_parks_facility_reference",
    "SPORTS_FIELD": "resolve_sports_facility_reference",
    "ROUTE_OR_STREET_SEGMENT": "build_route_geometry_review",
    "BOROUGH_ONLY": "request_more_source_evidence",
    "MALFORMED_SOURCE": "source_data_repair_review",
}

ADDRESS_RE = re.compile(r"\b\d{1,6}[A-Za-z]?(?:[- ]\d+)?\s+[A-Za-z0-9.' -]+\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|place|pl|court|ct|way|parkway|pkwy|highway|hwy)\b", re.I)
INTERSECTION_RE = re.compile(r"\b(?:at|and|&|/|corner of)\b", re.I)
ROUTE_RE = re.compile(r"\b(?:between|from)\b.+\b(?:and|to|through)\b", re.I)
PARK_RE = re.compile(r"\b(?:park|playground|recreation center|rec center|greenway)\b", re.I)
PARK_SUB_RE = re.compile(r"\b(?:lawn|field|court|ballfield|soccer|baseball|softball|basketball|tennis|track|pool|rink|pavilion|picnic|terrace|promenade)\b", re.I)
SPORT_RE = re.compile(r"\b(?:field|court|stadium|arena|ballfield|soccer|baseball|softball|basketball|football|hockey|tennis|track|athletic)\b", re.I)
VENUE_RE = re.compile(r"\b(?:theater|theatre|hall|center|centre|museum|gallery|library|school|college|university|church|synagogue|temple|club|hotel|restaurant|bar|cafe|arena|stadium)\b", re.I)
BOROUGH_ONLY = {"bronx", "brooklyn", "manhattan", "queens", "staten island", "new york", "nyc", "new york city"}


def text(value: Any) -> str:
    return str(value or "").strip()


def source(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("source")
    return value if isinstance(value, dict) else {}


def nycif(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("nycif")
    return value if isinstance(value, dict) else {}


def source_dataset(row: dict[str, Any]) -> str:
    return text(row.get("source_dataset") or source(row).get("dataset"))


def source_event_id(row: dict[str, Any]) -> str:
    return text(row.get("source_event_id") or source(row).get("source_event_id"))


def source_cemsid(row: dict[str, Any]) -> str:
    return text(row.get("source_cemsid") or source(row).get("source_cemsid") or row.get("cemsid"))


def location_text(row: dict[str, Any]) -> str:
    n = nycif(row)
    return text(
        n.get("source_location_text")
        or row.get("event_location")
        or row.get("location")
        or row.get("display_location")
        or row.get("venue_name")
        or row.get("address")
    )


def display_disposition(row: dict[str, Any]) -> str:
    return text(nycif(row).get("display_disposition") or row.get("display_disposition"))


def map_state(row: dict[str, Any]) -> str:
    return text(nycif(row).get("map_eligibility_state") or row.get("map_eligibility_state"))


def is_public_unresolved(row: dict[str, Any]) -> bool:
    state = map_state(row)
    role = text(row.get("event_role") or nycif(row).get("event_role") or "public_event")
    disposition = display_disposition(row)
    parent = row.get("parent_event_id")
    return (
        state in {"LIST_ONLY", "REVIEW_REQUIRED"}
        and role == "public_event"
        and parent in (None, "")
        and disposition not in {"suppressed", "child", "non_public"}
    )


def classify(row: dict[str, Any]) -> tuple[str, str]:
    loc = location_text(row)
    low = loc.casefold()
    cemsid = source_cemsid(row)
    venue_id = text(row.get("venue_id") or source(row).get("venue_id"))
    facility_id = text(row.get("facility_id") or source(row).get("facility_id"))

    if not loc:
        return "MALFORMED_SOURCE", "missing_location_text"
    if low in BOROUGH_ONLY or low == text(row.get("borough")).casefold():
        return "BOROUGH_ONLY", "location_claim_is_only_borough_or_city"
    if ROUTE_RE.search(loc):
        return "ROUTE_OR_STREET_SEGMENT", "route_or_segment_language"
    if cemsid:
        return "CEMSID", "native_cemsid_present"
    if facility_id:
        return "KNOWN_FACILITY", "native_facility_id_present"
    if venue_id:
        return "KNOWN_VENUE", "native_venue_id_present"
    if PARK_RE.search(loc) and PARK_SUB_RE.search(loc):
        return "PARK_SUBFACILITY", "park_and_subfacility_terms"
    if SPORT_RE.search(loc):
        return "SPORTS_FIELD", "sports_facility_terms"
    if ADDRESS_RE.search(loc):
        return "EXACT_ADDRESS", "street_address_pattern"
    if INTERSECTION_RE.search(loc) and len(loc.split()) >= 3:
        return "INTERSECTION", "intersection_pattern"
    if VENUE_RE.search(loc):
        return "KNOWN_VENUE", "venue_name_pattern"
    if len(loc) < 3:
        return "MALFORMED_SOURCE", "location_text_too_short"
    return "KNOWN_FACILITY", "named_place_requires_registry_resolution"


def occurrence_id(row: dict[str, Any]) -> str:
    try:
        return "|".join(str(part) for part in occurrence_key_v2(row))
    except Exception:
        return "|".join((source_dataset(row), source_event_id(row), text(row.get("start_date_time") or row.get("start"))))


def build(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unresolved = [row for row in rows if is_public_unresolved(row)]
    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    duplicate_ids = 0
    seen: set[str] = set()

    for row in unresolved:
        oid = occurrence_id(row)
        if oid in seen:
            duplicate_ids += 1
        seen.add(oid)
        bucket, reason = classify(row)
        counts[bucket] += 1
        state_counts[map_state(row)] += 1
        source_counts[source_dataset(row) or "unknown"] += 1
        output.append({
            "occurrence_id": oid,
            "source_dataset": source_dataset(row),
            "source_event_id": source_event_id(row),
            "source_cemsid": source_cemsid(row) or None,
            "title": row.get("title"),
            "start_date_time": row.get("start_date_time"),
            "borough": row.get("borough"),
            "event_location": location_text(row) or None,
            "current_map_state": map_state(row),
            "resolver_bucket": bucket,
            "classification_reason": reason,
            "next_resolver_step": NEXT_STEP[bucket],
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
        })

    qa_pass = (
        len(output) == len(unresolved)
        and sum(counts.values()) == len(unresolved)
        and not (set(counts) - set(BUCKETS))
        and duplicate_ids == 0
        and all(item["current_map_state"] in {"LIST_ONLY", "REVIEW_REQUIRED"} for item in output)
        and all(item["promotion_allowed"] is False for item in output)
    )
    report = {
        "schema_version": "NYCIF_UNRESOLVED_LOCATION_BACKLOG_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "eligible_unresolved_count": len(unresolved),
        "classified_count": len(output),
        "bucket_counts": dict(sorted(counts.items())),
        "map_state_counts": dict(sorted(state_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "duplicate_occurrence_count": duplicate_ids,
        "promotion_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "qa_pass": qa_pass,
        "operating_rule": "Report-only classification. No coordinate, public eligibility, or protected cache promotion occurs here.",
    }
    return output, report


def main() -> int:
    payload = json.loads(CANONICAL.read_text(encoding="utf-8"))
    rows = [row for row in extract_rows(payload) if isinstance(row, dict)]
    backlog, report = build(rows)
    OUT.write_text(json.dumps({"schema_version": report["schema_version"], "items": backlog}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["qa_pass"]:
        raise RuntimeError(f"unresolved location backlog QA failed: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
