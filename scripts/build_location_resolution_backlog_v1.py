#!/usr/bin/env python3
"""Classify unresolved public event locations without promoting coordinates.

This is a diagnostic/review artifact only. It never changes location_cache,
canonical event rows, map-ready geometry, or publication state.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
OUT = ROOT / "data" / "location_resolution_backlog_v1.json"
REPORT = ROOT / "data" / "location_resolution_backlog_v1_report.json"

BUCKETS = (
    "KNOWN_FACILITY", "KNOWN_VENUE", "CEMSID", "EXACT_ADDRESS", "INTERSECTION",
    "PARK_SUBFACILITY", "SPORTS_FIELD", "ROUTE_OR_STREET_SEGMENT", "BOROUGH_ONLY", "MALFORMED_SOURCE",
)
BOROUGHS = {"bronx", "brooklyn", "manhattan", "queens", "staten island", "new york", "new york city", "nyc"}
ADDRESS_RE = re.compile(r"^\s*\d+[a-zA-Z-]*\s+\S+")
INTERSECTION_RE = re.compile(r"\b(?:and|&|at)\b.*\b(?:st(?:reet)?|ave(?:nue)?|rd|road|blvd|boulevard|dr|drive|pl|place|way|pkwy|parkway)\b", re.I)
ROUTE_RE = re.compile(r"\b(?:between|from\b.+\bto\b|route|street closure|curb lane|roadway|march route|parade route)\b", re.I)
SPORTS_RE = re.compile(r"\b(?:soccer|baseball|softball|football|basketball|tennis|court|field|diamond|pitch)\b", re.I)
PARK_RE = re.compile(r"\b(?:park|playground|recreation center|rec center|lawn|greenway|garden|pool|beach)\b", re.I)
VENUE_RE = re.compile(r"\b(?:theater|theatre|hall|museum|gallery|library|school|college|university|church|synagogue|temple|club|hotel|restaurant|cafe|arena|stadium)\b", re.I)


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Read common repository JSON envelopes without importing legacy packages."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "rows", "items", "records", "occurrences", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def load_rows(path: Path) -> list[dict[str, Any]]:
    return extract_rows(json.loads(path.read_text(encoding="utf-8")))


def source_parts(row: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = str(row.get("source_dataset") or source.get("dataset") or "").strip()
    source_event_id = str(row.get("source_event_id") or row.get("event_id") or source.get("source_event_id") or "").strip()
    return source, dataset, source_event_id


def location_text(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    values = (nycif.get("source_location_text"), row.get("event_location"), row.get("location"), row.get("venue_name"), row.get("address"), row.get("street_address"))
    for value in values:
        value_text = str(value or "").strip()
        if value_text:
            return value_text
    return ""


def classify_row(row: dict[str, Any]) -> tuple[str, list[str]]:
    source, dataset, source_event_id = source_parts(row)
    title = str(row.get("title") or "").strip()
    start = str(row.get("start_date_time") or row.get("start_at") or "").strip()
    place = location_text(row)
    lower = place.lower().strip()
    missing: list[str] = []
    if not title: missing.append("missing_title")
    if not start: missing.append("missing_start")
    if not dataset: missing.append("missing_source_dataset")
    if not source_event_id: missing.append("missing_source_event_id")
    if missing:
        return "MALFORMED_SOURCE", missing
    borough = str(row.get("borough") or "").strip().lower()
    if not lower or lower in BOROUGHS or (borough and lower == borough):
        return "BOROUGH_ONLY", ["borough_only_location"]
    if ROUTE_RE.search(place):
        return "ROUTE_OR_STREET_SEGMENT", ["route_language"]
    cemsid = row.get("source_cemsid") or source.get("source_cemsid") or source.get("cemsid")
    if cemsid:
        return "CEMSID", ["source_cemsid"]
    facility_id = row.get("facility_id") or row.get("facility_number") or source.get("facility_id")
    facility_name = row.get("facility_name") or source.get("facility_name")
    if facility_id or facility_name:
        return "KNOWN_FACILITY", ["facility_id" if facility_id else "facility_name"]
    venue_id = row.get("venue_id") or source.get("venue_id")
    venue_name = row.get("venue_name")
    if venue_id or venue_name:
        return "KNOWN_VENUE", ["venue_id" if venue_id else "venue_name"]
    if PARK_RE.search(place) and (":" in place or "(" in place or SPORTS_RE.search(place)):
        return "PARK_SUBFACILITY", ["park_subfacility_language"]
    if SPORTS_RE.search(place):
        return "SPORTS_FIELD", ["sports_location_language"]
    if ADDRESS_RE.search(place):
        return "EXACT_ADDRESS", ["street_number_pattern"]
    if INTERSECTION_RE.search(place):
        return "INTERSECTION", ["intersection_language"]
    if VENUE_RE.search(place):
        return "KNOWN_VENUE", ["venue_name_pattern"]
    return "KNOWN_FACILITY", ["named_place_requires_registry_match"]


def occurrence_id(row: dict[str, Any]) -> str:
    value = row.get("occurrence_id")
    if value:
        return str(value)
    return "|".join(str(part) for part in occurrence_key_v2(row))


def is_unresolved_public(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    state = str(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "").strip()
    if state not in {"LIST_ONLY", "REVIEW_REQUIRED"}:
        return False
    title = str(row.get("title") or "")
    if re.match(r"^\s*(?:CANCELED|CANCELLED)\s*:", title, re.I):
        return False
    role = str(row.get("event_role") or nycif.get("event_role") or "public_event").strip()
    if role != "public_event" or row.get("parent_event_id") not in (None, ""):
        return False
    disposition = str(nycif.get("display_disposition") or row.get("display_disposition") or "").lower()
    return disposition not in {"suppressed", "private", "internal_only", "non_public", "child"}


def build(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    queue: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    states: Counter[str] = Counter()
    ids: set[str] = set()
    duplicate_ids = 0
    for row in rows:
        if not is_unresolved_public(row):
            continue
        oid = occurrence_id(row)
        if oid in ids:
            duplicate_ids += 1
            continue
        ids.add(oid)
        _source, dataset, source_event_id = source_parts(row)
        nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "")
        bucket, evidence = classify_row(row)
        counts[bucket] += 1
        states[state] += 1
        queue.append({
            "occurrence_id": oid, "source_dataset": dataset, "source_event_id": source_event_id,
            "title": row.get("title"), "start_date_time": row.get("start_date_time") or row.get("start_at"),
            "borough": row.get("borough"), "event_location": location_text(row) or None,
            "resolution_bucket": bucket, "classification_evidence": evidence,
            "current_map_eligibility_state": state, "manual_review_status": "pending",
            "promotion_allowed": False, "public_map_modified": False,
            "location_cache_modified": False, "staged_feed_modified": False,
        })
    queue.sort(key=lambda x: (x["resolution_bucket"], str(x.get("borough") or ""), str(x.get("start_date_time") or ""), x["occurrence_id"]))
    report = {
        "schema_version": "NYCIF_LOCATION_RESOLUTION_BACKLOG_V1", "generated_at_utc": generated,
        "unresolved_public_occurrence_count": len(queue), "map_state_counts": dict(sorted(states.items())),
        "bucket_counts": {bucket: counts.get(bucket, 0) for bucket in BUCKETS},
        "duplicate_occurrence_count": duplicate_ids, "promotion_attempt_count": 0,
        "public_map_modified": False, "location_cache_modified": False, "staged_feed_modified": False,
        "qa_pass": duplicate_ids == 0 and len(queue) == sum(counts.values()),
        "operating_rule": "Diagnostic classification only; no coordinates are approved or promoted by this artifact.",
    }
    return queue, report


def main() -> int:
    queue, report = build(load_rows(CANONICAL))
    OUT.write_text(json.dumps({"schema_version": report["schema_version"], "generated_at_utc": report["generated_at_utc"], "rows": queue}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["qa_pass"]:
        raise RuntimeError(f"location backlog classification QA failed: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
