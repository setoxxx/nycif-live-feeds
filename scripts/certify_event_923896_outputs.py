#!/usr/bin/env python3
"""Certify Event 923896 across approved map pages, list export and health."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "923896"
REQUIRED_DATE = "2026-08-01"
REPORT = ROOT / "data" / "reports" / "event_923896_snapshot_recovery_certificate.json"


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def source_id(event: dict[str, Any]) -> str:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return str(
        event.get("source_event_id")
        or source.get("source_event_id")
        or source.get("event_id")
        or ""
    ).strip()


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def inspect(event: dict[str, Any], surface: str) -> dict[str, Any]:
    failures: list[str] = []
    start = event.get("start_date") or event.get("start_date_time") or event.get("start")
    borough = event.get("borough")
    location_value = event.get("display_location") or event.get("location") or event.get("address") or ""
    location_object = event.get("location") if isinstance(event.get("location"), dict) else {}
    if isinstance(location_value, dict):
        location_value = " ".join(
            str(location_value.get(key) or "")
            for key in ("name", "display_name", "address", "street", "description")
        )
    lat = event.get("latitude", event.get("lat", location_object.get("latitude", location_object.get("lat"))))
    lng = event.get(
        "longitude",
        event.get("lng", location_object.get("longitude", location_object.get("lng", location_object.get("lon")))),
    )
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        lat, lng = None, None
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    coordinate_status = event.get("coordinate_status") or nycif.get("coordinate_status")

    if not str(start or "").startswith(REQUIRED_DATE):
        failures.append(f"{surface}: wrong date {start!r}")
    if normalized(borough) != "brooklyn":
        failures.append(f"{surface}: wrong borough {borough!r}")
    location_norm = normalized(location_value)
    for token in ("east 74 street", "avenue u", "avenue t"):
        if token not in location_norm:
            failures.append(f"{surface}: missing {token!r}")
    if lat is None or lng is None:
        failures.append(f"{surface}: missing coordinates")
    else:
        if not 40.60 <= lat <= 40.64:
            failures.append(f"{surface}: latitude {lat}")
        if not -73.93 <= lng <= -73.88:
            failures.append(f"{surface}: longitude {lng}")
    if coordinate_status and str(coordinate_status).lower() != "map_ready":
        failures.append(f"{surface}: coordinate status {coordinate_status!r}")
    return {
        "surface": surface,
        "event_id": event.get("id"),
        "start": start,
        "borough": borough,
        "location": location_value,
        "latitude": lat,
        "longitude": lng,
        "coordinate_status": coordinate_status,
        "failures": failures,
    }


def main() -> int:
    page_matches: list[tuple[str, dict[str, Any]]] = []
    for page in sorted((ROOT / "data" / "schema-v1-discovery" / "approved" / "pages").glob("page-*.json")):
        for event in rows(load(page, {})):
            if source_id(event) == EVENT_ID:
                page_matches.append((page.name, event))
    list_matches = [
        event
        for event in rows(load(ROOT / "data" / "events_discovery_v02_approved.json", {}))
        if source_id(event) == EVENT_ID
    ]
    health = load(ROOT / "status" / "nycif-daily-data-health.json", {}) or {}
    reconciliation = load(ROOT / "data" / "events_discovery_reconciliation_v02.json", {}) or {}
    health_event = (((health.get("required_event_checks") or {}).get("event_923896")) or {})

    failures: list[str] = []
    if len(page_matches) != 1:
        failures.append(f"approved map pages: expected 1, found {len(page_matches)}")
    if len(list_matches) != 1:
        failures.append(f"approved list: expected 1, found {len(list_matches)}")
    page_check = inspect(page_matches[0][1], f"approved page {page_matches[0][0]}") if page_matches else None
    list_check = inspect(list_matches[0], "approved list") if list_matches else None
    for check in (page_check, list_check):
        if check:
            failures.extend(check["failures"])
    if health.get("status") != "READY" or health.get("release_ready") is not True:
        failures.append(f"health is not READY: {health.get('status')!r}")
    if health.get("schema_version") != "1.4.0":
        failures.append(f"health schema is not 1.4.0: {health.get('schema_version')!r}")
    if health_event.get("qa_pass") is not True or int(health_event.get("match_count") or 0) != 1:
        failures.append(f"health event certificate failed: {health_event}")
    if reconciliation.get("reconciles_strict") is not True:
        failures.append("strict reconciliation failed")

    report = {
        "artifact_type": "nycif_stage7_completion_certificate",
        "schema_version": "1.0.0",
        "source_event_id": EVENT_ID,
        "required_date": REQUIRED_DATE,
        "qa_pass": not failures,
        "failures": failures,
        "approved_page_match_count": len(page_matches),
        "approved_list_match_count": len(list_matches),
        "approved_page": page_matches[0][0] if len(page_matches) == 1 else None,
        "page_check": page_check,
        "list_check": list_check,
        "health_status": health.get("status"),
        "health_schema_version": health.get("schema_version"),
        "health_event_check": health_event,
        "strict_reconciliation": reconciliation.get("reconciles_strict"),
        "approved_manifest_total": (
            load(ROOT / "data" / "schema-v1-discovery" / "approved" / "manifest.json", {}) or {}
        ).get("total"),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
