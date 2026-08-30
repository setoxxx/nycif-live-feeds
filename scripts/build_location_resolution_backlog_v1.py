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
    from scripts.discovery_v02 import extract_rows
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
OUT = ROOT / "data" / "location_resolution_backlog_v1.json"
REPORT = ROOT / "data" / "location_resolution_backlog_v1_report.json"

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

BOROUGHS = {"bronx", "brooklyn", "manhattan", "queens", "staten island", "new york"}
ADDRESS_RE = re.compile(r"^\s*\d+[a-zA-Z-]*\s+\S+")
INTERSECTION_RE = re.compile(
    r"\b(?:and|&|at)\b.*\b(?:st(?:reet)?|ave(?:nue)?|rd|road|blvd|boulevard|dr|drive|pl|place|way|pkwy|parkway)\b",
    re.I,
)
ROUTE_RE = re.compile(
    r"\b(?:between|from\b.+\bto\b|route|street closure|curb lane|roadway|march route|parade route)\b",
    re.I,
)
SPORTS_RE = re.compile(r"\b(?:soccer|baseball|softball|football|basketball|tennis|court|field|diamond|pitch)\b", re.I)
PARK_RE = re.compile(r"\b(?:park|playground|recreation center|rec center|lawn|greenway|garden|pool|beach)\b", re.I)


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in extract_rows(payload) if isinstance(row, dict)]


def source_parts(row: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = str(row.get("source_dataset") or source.get("dataset") or "").strip()
    source_event_id = str(
        row.get("source_event_id")
        or row.get("event_id")
        or source.get("source_event_id")
        or ""
    ).strip()
    return source, dataset, source_event_id


def location_text(row: dict[str, Any]) -> str:
    values = (
        row.get("event_location"),
        row.get("location"),
        row.get("venue_name"),
        row.get("address"),
        row.get("street_address"),
    )
    return " | ".join(str(v).strip() for v in values if str(v or "").strip())


def classify_row(row: dict[str, Any]) -> tuple[str, list[str]]:
    source, dataset, source_event_id = source_parts(row)
    title = str(row.get("title") or "").strip()
    start = str(row.get("start_date_time") or row.get("start_at") or "").strip()
    text = location_text(row)
    lower = text.lower().strip()
    evidence: list[str] = []

    if not title or not start or not dataset or not source_event_id:
        if not title:
            evidence.append("missing_title")
        if not start:
            evidence.append("missing_start")
        if not dataset:
            evidence.append("missing_source_dataset")
        if not source_event_id:
            evidence.append("missing_source_event_id")
        return "MALFORMED_SOURCE", evidence

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

    if ROUTE_RE.search(text):
        return "ROUTE_OR_STREET_SEGMENT", ["route_language"]

    if SPORTS_RE.search(text):
        return "SPORTS_FIELD", ["sports_location_language"]

    if PARK_RE.search(text) and (":" in text or "(" in text or ")" in text or len(text.split()) >= 3):
        return "PARK_SUBFACILITY", ["park_subfacility_language"]

    if ADDRESS_RE.search(text):
        return "EXACT_ADDRESS", ["street_number_pattern"]

    if INTERSECTION_RE.search(text):
        return "INTERSECTION", ["intersection_language"]

    borough = str(row.get("borough") or "").strip().lower()
    compact = lower.replace(" | ", " ").strip()
    if not compact or compact in BOROUGHS or (borough and compact == borough):
        return "BOROUGH_ONLY", ["borough_only_location"]

    return "KNOWN_FACILITY", ["named_place_requires_registry_match"]


def occurrence_id(row: dict[str, Any]) -> str:
    value = row.get("occurrence_id") or row.get("id")
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
    disposition = str(nycif.get("display_disposition") or row.get("display_disposition") or "").lower()
    return disposition not in {"suppressed", "private", "internal_only"}


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
        source, dataset, source_event_id = source_parts(row)
        nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "")
        bucket, evidence = classify_row(row)
        counts[bucket] += 1
        states[state] += 1
        queue.append(
            {
                "occurrence_id": oid,
                "source_dataset": dataset,
                "source_event_id": source_event_id,
                "title": row.get("title"),
                "start_date_time": row.get("start_date_time") or row.get("start_at"),
                "borough": row.get("borough"),
                "event_location": row.get("event_location") or row.get("location"),
                "resolution_bucket": bucket,
                "classification_evidence": evidence,
                "current_map_eligibility_state": state,
                "manual_review_status": "pending",
                "promotion_allowed": False,
                "public_map_modified": False,
                "location_cache_modified": False,
                "staged_feed_modified": False,
            }
        )

    queue.sort(key=lambda x: (x["resolution_bucket"], str(x.get("borough") or ""), str(x.get("start_date_time") or ""), x["occurrence_id"]))
    report = {
        "schema_version": "NYCIF_LOCATION_RESOLUTION_BACKLOG_V1",
        "generated_at_utc": generated,
        "unresolved_public_occurrence_count": len(queue),
        "map_state_counts": dict(sorted(states.items())),
        "bucket_counts": {bucket: counts.get(bucket, 0) for bucket in BUCKETS},
        "duplicate_occurrence_count": duplicate_ids,
        "promotion_attempt_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
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
