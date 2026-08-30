#!/usr/bin/env python3
"""Classify unresolved canonical event locations without promoting coordinates.

The V3 map-state status counts every canonical occurrence, while only a subset is
reader-facing. This diagnostic classifies every LIST_ONLY or REVIEW_REQUIRED
canonical occurrence and records whether each row is reader-facing public.
Cross-artifact state reconciliation is enforced only when canonical and V3
status belong to the same release window; stale checked-in artifacts are labeled
instead of being falsely compared. No coordinates or publication state change.
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
V3_STATUS = ROOT / "data" / "reader-safe" / "national-map-events-v03-status.json"
OUT = ROOT / "data" / "location_resolution_backlog_v1.json"
REPORT = ROOT / "data" / "location_resolution_backlog_v1_report.json"

BUCKETS = (
    "KNOWN_FACILITY", "KNOWN_VENUE", "CEMSID", "EXACT_ADDRESS", "INTERSECTION",
    "PARK_SUBFACILITY", "SPORTS_FIELD", "ROUTE_OR_STREET_SEGMENT", "BOROUGH_ONLY", "MALFORMED_SOURCE",
)
BOROUGHS = {"bronx", "brooklyn", "manhattan", "queens", "staten island", "new york", "new york city", "nyc"}
ADDRESS_RE = re.compile(r"^\s*(?!\d+(?:st|nd|rd|th)\b)\d+[a-zA-Z-]*\s+\S+", re.I)
ORDINAL_STREET_RE = re.compile(
    r"^\s*\d+(?:st|nd|rd|th)\s+(?:st(?:reet)?|ave(?:nue)?|rd|road|blvd|boulevard|dr|drive|pl|place|way|pkwy|parkway)\b",
    re.I,
)
INTERSECTION_RE = re.compile(r"\b(?:and|&|at)\b.*\b(?:st(?:reet)?|ave(?:nue)?|rd|road|blvd|boulevard|dr|drive|pl|place|way|pkwy|parkway)\b", re.I)
ROUTE_RE = re.compile(r"\b(?:between|from\b.+\bto\b|route|street closure|curb lane|roadway|march route|parade route)\b", re.I)
SPORTS_RE = re.compile(r"\b(?:soccer|baseball|softball|football|basketball|tennis|court|field|diamond|pitch)\b", re.I)
PARK_RE = re.compile(r"\b(?:park|playground|recreation center|rec center|lawn|greenway|garden|pool|beach)\b", re.I)
VENUE_RE = re.compile(r"\b(?:theater|theatre|hall|museum|gallery|library|school|college|university|church|synagogue|temple|club|hotel|restaurant|cafe|arena|stadium)\b", re.I)


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Dependency-light equivalent of discovery_v02.extract_rows."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "data", "rows", "features", "records", "items", "occurrences"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        if key == "features":
            rows: list[dict[str, Any]] = []
            for feature in value:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
                row = dict(props)
                row["_geojson_geometry"] = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
                rows.append(row)
            return rows
        return [row for row in value if isinstance(row, dict)]
    return []


def load_payload(path: Path) -> tuple[Any, list[dict[str, Any]], str | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    generated = str(payload.get("generated_at_utc") or "").strip() if isinstance(payload, dict) else ""
    return payload, extract_rows(payload), generated or None


def parse_generated(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def same_release_window(canonical_generated: Any, status_generated: Any, max_skew_seconds: int = 900) -> bool:
    left = parse_generated(canonical_generated)
    right = parse_generated(status_generated)
    return bool(left and right and abs((left - right).total_seconds()) <= max_skew_seconds)


def source_parts(row: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = str(row.get("source_dataset") or source.get("dataset") or "").strip()
    source_event_id = str(row.get("source_event_id") or row.get("event_id") or source.get("source_event_id") or "").strip()
    return source, dataset, source_event_id


def location_text(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    values = (
        nycif.get("source_location_text"), row.get("event_location"), row.get("location"),
        row.get("venue_name"), row.get("address"), row.get("street_address"),
    )
    for value in values:
        value_text = str(value or "").strip()
        if value_text:
            return value_text
    return ""


def map_state(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    state = str(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "REVIEW_REQUIRED").strip().upper()
    return state if state in {"MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY"} else "REVIEW_REQUIRED"


def reader_public(row: dict[str, Any]) -> bool:
    title = str(row.get("title") or "")
    if re.match(r"^\s*(?:CANCELED|CANCELLED)\s*:", title, re.I):
        return False
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    role = str(row.get("event_role") or nycif.get("event_role") or "public_event").strip()
    if role != "public_event" or row.get("parent_event_id") not in (None, ""):
        return False
    disposition = str(nycif.get("display_disposition") or row.get("display_disposition") or "").strip().lower()
    return disposition in {"standalone_public_event", "list_only"}


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
    if ROUTE_RE.search(place) or ORDINAL_STREET_RE.search(place):
        reason = "route_language" if ROUTE_RE.search(place) else "ordinal_street_without_house_number"
        return "ROUTE_OR_STREET_SEGMENT", [reason]
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
    if INTERSECTION_RE.search(place):
        return "INTERSECTION", ["intersection_language"]
    if ADDRESS_RE.search(place):
        return "EXACT_ADDRESS", ["street_number_pattern"]
    if VENUE_RE.search(place):
        return "KNOWN_VENUE", ["venue_name_pattern"]
    return "KNOWN_FACILITY", ["named_place_requires_registry_match"]


def occurrence_id(row: dict[str, Any]) -> str:
    value = row.get("occurrence_id")
    if value:
        return str(value)
    return "|".join(str(part) for part in occurrence_key_v2(row))


def build(rows: list[dict[str, Any]], *, expected_state_counts: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    queue: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    public_counts: Counter[str] = Counter()
    states: Counter[str] = Counter()
    all_states: Counter[str] = Counter()
    ids: set[str] = set()
    duplicate_ids = 0
    cancelled_unresolved = 0

    for row in rows:
        state = map_state(row)
        all_states[state] += 1
        if state not in {"LIST_ONLY", "REVIEW_REQUIRED"}:
            continue
        title = str(row.get("title") or "")
        if re.match(r"^\s*(?:CANCELED|CANCELLED)\s*:", title, re.I):
            cancelled_unresolved += 1
            continue
        oid = occurrence_id(row)
        if oid in ids:
            duplicate_ids += 1
            continue
        ids.add(oid)
        _source, dataset, source_event_id = source_parts(row)
        bucket, evidence = classify_row(row)
        is_public = reader_public(row)
        counts[bucket] += 1
        states[state] += 1
        if is_public:
            public_counts[bucket] += 1
        queue.append({
            "occurrence_id": oid, "source_dataset": dataset, "source_event_id": source_event_id,
            "title": row.get("title"), "start_date_time": row.get("start_date_time") or row.get("start_at"),
            "borough": row.get("borough"), "event_location": location_text(row) or None,
            "resolution_bucket": bucket, "classification_evidence": evidence,
            "current_map_eligibility_state": state, "reader_public": is_public,
            "event_role": row.get("event_role"),
            "display_disposition": (row.get("nycif") or {}).get("display_disposition") if isinstance(row.get("nycif"), dict) else row.get("display_disposition"),
            "manual_review_status": "pending", "promotion_allowed": False,
            "public_map_modified": False, "location_cache_modified": False, "staged_feed_modified": False,
        })

    queue.sort(key=lambda x: (not bool(x["reader_public"]), x["resolution_bucket"], str(x.get("borough") or ""), str(x.get("start_date_time") or ""), x["occurrence_id"]))
    expected = expected_state_counts or {}
    expected_unresolved = int(expected.get("LIST_ONLY") or 0) + int(expected.get("REVIEW_REQUIRED") or 0)
    canonical_unresolved_before_cancel = all_states.get("LIST_ONLY", 0) + all_states.get("REVIEW_REQUIRED", 0)
    state_count_matches_v3 = not expected or canonical_unresolved_before_cancel == expected_unresolved
    public_unresolved = sum(public_counts.values())
    report = {
        "schema_version": "NYCIF_LOCATION_RESOLUTION_BACKLOG_V1", "generated_at_utc": generated,
        "canonical_row_count": len(rows),
        "all_canonical_map_state_counts": dict(sorted(all_states.items())),
        "unresolved_canonical_before_cancel_suppression": canonical_unresolved_before_cancel,
        "cancelled_unresolved_suppressed": cancelled_unresolved,
        "unresolved_canonical_occurrence_count": len(queue),
        "unresolved_public_occurrence_count": public_unresolved,
        "unresolved_nonpublic_occurrence_count": len(queue) - public_unresolved,
        "map_state_counts": dict(sorted(states.items())),
        "bucket_counts": {bucket: counts.get(bucket, 0) for bucket in BUCKETS},
        "public_bucket_counts": {bucket: public_counts.get(bucket, 0) for bucket in BUCKETS},
        "expected_v3_unresolved_state_count": expected_unresolved if expected else None,
        "canonical_state_count_matches_v3_status": state_count_matches_v3 if expected else None,
        "duplicate_occurrence_count": duplicate_ids, "promotion_attempt_count": 0,
        "public_map_modified": False, "location_cache_modified": False, "staged_feed_modified": False,
        "qa_pass": duplicate_ids == 0 and len(queue) == sum(counts.values()) and state_count_matches_v3,
        "operating_rule": "Diagnostic classification only; all unresolved canonical rows are classified, reader-public scope is labeled separately, and no coordinates are approved or promoted by this artifact.",
    }
    return queue, report


def main() -> int:
    canonical_payload, rows, canonical_generated = load_payload(CANONICAL)
    status = json.loads(V3_STATUS.read_text(encoding="utf-8")) if V3_STATUS.exists() else {}
    status_generated = status.get("generated_at_utc") if isinstance(status, dict) else None
    comparable = same_release_window(canonical_generated, status_generated)
    expected_state_counts = status.get("map_state_counts") if comparable and isinstance(status.get("map_state_counts"), dict) else None
    queue, report = build(rows, expected_state_counts=expected_state_counts)
    report["canonical_generated_at_utc"] = canonical_generated
    report["v3_status_generated_at_utc"] = status_generated
    report["v3_status_comparable"] = comparable
    report["canonical_artifact_type"] = canonical_payload.get("artifact_type") if isinstance(canonical_payload, dict) else None
    OUT.write_text(json.dumps({"schema_version": report["schema_version"], "generated_at_utc": report["generated_at_utc"], "rows": queue}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["qa_pass"]:
        raise RuntimeError(f"location backlog classification QA failed: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
