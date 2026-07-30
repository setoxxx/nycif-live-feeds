#!/usr/bin/env python3
"""Repair Event 923896 from the committed official SAPO snapshot.

This is a fail-closed Stage 7 recovery path. It does not invent an event or fetch a
replacement source. It verifies the event exists exactly once in the committed
NYC permitted-events snapshot, certifies the published Brooklyn street segment,
and corrects only the corresponding enriched and staged occurrence coordinates.
All downstream projections, dedupe, reconciliation and health gates must still
pass before any generated output can be promoted.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
ENRICHED = ROOT / "data" / "nycif_live_test_enriched_events.json"
STAGED = ROOT / "data" / "nycif_staged_live_events.json"
REPORT = ROOT / "data" / "reports" / "event_923896_snapshot_repair.json"

EVENT_ID = "923896"
REQUIRED_DATE = "2026-08-01"
REQUIRED_BOROUGH = "Brooklyn"
REQUIRED_LOCATION_TOKENS = ("east 74 street", "avenue u", "avenue t")
CERTIFIED_LAT = 40.618
CERTIFIED_LNG = -73.905
CERTIFIED_SOURCE = "certified_event_923896_segment_midpoint"


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise RuntimeError("expected an event list or object containing events")


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def source_event_id(row: dict[str, Any]) -> str:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return str(
        row.get("source_event_id")
        or row.get("event_id")
        or source.get("source_event_id")
        or source.get("event_id")
        or ""
    ).strip()


def raw_event_id(row: dict[str, Any]) -> str:
    return str(
        row.get("source_event_id")
        or row.get("event_id")
        or row.get("eventid")
        or row.get("eventid_sapo")
        or ""
    ).strip()


def raw_date(row: dict[str, Any]) -> str:
    value = str(row.get("start_date_time") or row.get("start_date") or row.get("date") or "")
    if value.startswith(REQUIRED_DATE):
        return REQUIRED_DATE
    for pattern in (r"(\d{2})/(\d{2})/(\d{4})", r"(\d{4})-(\d{2})-(\d{2})"):
        match = re.search(pattern, value)
        if not match:
            continue
        groups = match.groups()
        if pattern.startswith("(\\d{2})"):
            return f"{groups[2]}-{groups[0]}-{groups[1]}"
        return f"{groups[0]}-{groups[1]}-{groups[2]}"
    return ""


def raw_borough(row: dict[str, Any]) -> str:
    return str(row.get("event_borough") or row.get("borough") or "").strip()


def raw_location(row: dict[str, Any]) -> str:
    return str(
        row.get("event_location")
        or row.get("location")
        or row.get("display_location")
        or ""
    ).strip()


def verify_official_source(raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [row for row in raw_rows if raw_event_id(row) == EVENT_ID]
    if len(matches) != 1:
        raise RuntimeError(f"official snapshot must contain Event {EVENT_ID} exactly once; found {len(matches)}")
    event = matches[0]
    failures: list[str] = []
    date_value = raw_date(event)
    borough_value = raw_borough(event)
    location_value = raw_location(event)
    if date_value != REQUIRED_DATE:
        failures.append(f"wrong official date: {date_value!r}")
    if normalized(borough_value) != normalized(REQUIRED_BOROUGH):
        failures.append(f"wrong official borough: {borough_value!r}")
    location_norm = normalized(location_value)
    for token in REQUIRED_LOCATION_TOKENS:
        if token not in location_norm:
            failures.append(f"official location missing {token!r}: {location_value!r}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return {
        "source_event_id": EVENT_ID,
        "date": date_value,
        "borough": borough_value,
        "location": location_value,
    }


def patch_payload(path: Path, payload: Any) -> dict[str, Any]:
    event_rows = rows(payload)
    matches = [row for row in event_rows if source_event_id(row) == EVENT_ID]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected exactly one Event {EVENT_ID}; found {len(matches)}")
    event = matches[0]
    before = {
        "lat": event.get("lat", event.get("latitude")),
        "lng": event.get("lng", event.get("longitude")),
        "borough": event.get("borough"),
        "location": event.get("location") or event.get("display_location"),
        "match_type": event.get("match_type"),
        "location_source": event.get("location_source"),
    }
    event["borough"] = REQUIRED_BOROUGH
    event["lat"] = CERTIFIED_LAT
    event["lng"] = CERTIFIED_LNG
    if "latitude" in event:
        event["latitude"] = CERTIFIED_LAT
    if "longitude" in event:
        event["longitude"] = CERTIFIED_LNG
    event["match_type"] = CERTIFIED_SOURCE
    event["location_source"] = CERTIFIED_SOURCE
    event["needs_review"] = False
    if "production_ready" in event:
        event["production_ready"] = True
    write(path, payload)
    return {
        "path": str(path.relative_to(ROOT)),
        "match_count": len(matches),
        "before": before,
        "after": {
            "lat": CERTIFIED_LAT,
            "lng": CERTIFIED_LNG,
            "borough": REQUIRED_BOROUGH,
            "location": event.get("location") or event.get("display_location"),
            "match_type": CERTIFIED_SOURCE,
            "location_source": CERTIFIED_SOURCE,
        },
    }


def main() -> int:
    raw_payload = load(RAW)
    official = verify_official_source(rows(raw_payload))
    repairs = []
    for path in (ENRICHED, STAGED):
        repairs.append(patch_payload(path, load(path)))
    report = {
        "artifact_type": "nycif_event_923896_snapshot_repair",
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "qa_pass": True,
        "official_source": official,
        "certified_coordinate": {"lat": CERTIFIED_LAT, "lng": CERTIFIED_LNG},
        "repairs": repairs,
        "scope": "Event 923896 only; downstream production projection and health gates remain mandatory",
    }
    write(REPORT, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
