#!/usr/bin/env python3
"""Build the launch-blocking daily data health contract for God View.

The report distinguishes a freshly regenerated wrapper from genuinely fresh,
successfully fetched source data. Every JSON family loaded by the public map or
News Desk overlays is included, including auxiliary overlays served from the
Field Desk repository. The daily production workflow must stop before committing
public feed artifacts unless this script returns success.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATUS = ROOT / "status"
OUT = STATUS / "nycif-daily-data-health.json"
FIELD_DESK_OVERLAY_HEALTH = STATUS / "nycif-field-desk-overlay-health.json"
APPROVED_PAGES = DATA / "schema-v1-discovery" / "approved" / "pages"
MAX_SOURCE_AGE_HOURS = 36.0
REQUIRED_EVENT_ID = "923896"
REQUIRED_EVENT_DATE = "2026-08-01"


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def timestamp(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("generated_at_utc", "generated_at", "last_run_utc"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_hours(value: str | None) -> float | None:
    parsed = parse_utc(value)
    if not parsed:
        return None
    return round((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 2)


def first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload.get(key)
    return None


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def source_status(
    name: str,
    path: Path,
    count_keys: tuple[str, ...],
    *,
    require_live_mode: bool = False,
) -> dict[str, Any]:
    payload = load(path, {}) or {}
    generated = timestamp(payload)
    age = age_hours(generated)
    qa_pass = bool(payload.get("qa_pass", True))
    fetch_mode = str(payload.get("fetch_mode") or "live")
    live_mode = not require_live_mode or fetch_mode == "live"
    fresh = age is not None and 0 <= age <= MAX_SOURCE_AGE_HOURS
    return {
        "name": name,
        "artifact": str(path.relative_to(ROOT)),
        "generated_at_utc": generated,
        "age_hours": age,
        "max_age_hours": MAX_SOURCE_AGE_HOURS,
        "qa_pass": qa_pass,
        "fetch_mode": fetch_mode,
        "live_fetch": live_mode,
        "fresh": fresh and qa_pass and live_mode,
        "record_count": first_value(payload, count_keys),
        "error": payload.get("error") or payload.get("live_fetch_error"),
    }


def artifact_status(
    name: str,
    path: Path,
    count_keys: tuple[str, ...],
    *,
    require_qa: bool = False,
) -> dict[str, Any]:
    payload = load(path, {}) or {}
    generated = timestamp(payload)
    age = age_hours(generated)
    qa_pass = bool(payload.get("qa_pass", True))
    fresh = age is not None and 0 <= age <= MAX_SOURCE_AGE_HOURS
    return {
        "name": name,
        "artifact": str(path.relative_to(ROOT)),
        "generated_at_utc": generated,
        "age_hours": age,
        "qa_pass": qa_pass,
        "fresh": fresh and (qa_pass or not require_qa),
        "record_count": first_value(payload, count_keys),
    }


def blocker(code: str, message: str, artifact: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "critical",
        "message": message,
        "artifact": artifact,
    }


def event_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def event_source_id(event: dict[str, Any]) -> str:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return str(
        event.get("source_event_id")
        or source.get("source_event_id")
        or source.get("event_id")
        or ""
    ).strip()


def event_location_text(event: dict[str, Any]) -> str:
    value = event.get("display_location") or event.get("location") or event.get("address") or ""
    if isinstance(value, dict):
        value = " ".join(
            str(value.get(key) or "")
            for key in ("name", "display_name", "address", "street", "description")
        )
    return str(value)


def event_coordinates(event: dict[str, Any]) -> tuple[float | None, float | None]:
    location = event.get("location") if isinstance(event.get("location"), dict) else {}
    lat_value = event.get("latitude")
    if lat_value is None:
        lat_value = event.get("lat")
    if lat_value is None:
        lat_value = location.get("latitude") or location.get("lat")
    lng_value = event.get("longitude")
    if lng_value is None:
        lng_value = event.get("lng")
    if lng_value is None:
        lng_value = location.get("longitude") or location.get("lng") or location.get("lon")
    try:
        return float(lat_value), float(lng_value)
    except (TypeError, ValueError):
        return None, None


def required_event_status(pages_root: Path = APPROVED_PAGES) -> dict[str, Any]:
    """Prove that required event 923896 is public exactly once with its Brooklyn pin."""
    matches: list[tuple[str, dict[str, Any]]] = []
    page_files = sorted(pages_root.glob("page-*.json")) if pages_root.exists() else []
    for page in page_files:
        for event in event_rows(load(page, {})):
            if event_source_id(event) == REQUIRED_EVENT_ID:
                matches.append((page.name, event))

    failures: list[str] = []
    if len(matches) != 1:
        failures.append(f"expected exactly one approved occurrence; found {len(matches)}")

    page_name = None
    event_id = None
    start_value = None
    borough = None
    location_text = None
    latitude = None
    longitude = None
    coordinate_status = None

    if matches:
        page_name, event = matches[0]
        event_id = event.get("id")
        start_value = event.get("start_date") or event.get("start_date_time") or event.get("start")
        borough = event.get("borough")
        if not borough and isinstance(event.get("location"), dict):
            borough = event["location"].get("borough")
        location_text = event_location_text(event)
        latitude, longitude = event_coordinates(event)
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        coordinate_status = event.get("coordinate_status") or nycif.get("coordinate_status")

        if not str(start_value or "").startswith(REQUIRED_EVENT_DATE):
            failures.append(f"occurrence date is {start_value!r}, expected {REQUIRED_EVENT_DATE}")
        if normalized_text(borough) != "brooklyn":
            failures.append(f"borough is {borough!r}, expected Brooklyn")

        normalized_location = normalized_text(location_text)
        for required_text in ("east 74 street", "avenue u", "avenue t"):
            if required_text not in normalized_location:
                failures.append(f"location is missing {required_text!r}: {location_text!r}")

        if latitude is None or longitude is None:
            failures.append("approved occurrence has no numeric coordinates")
        else:
            if not 40.60 <= latitude <= 40.64:
                failures.append(f"latitude {latitude} is outside the certified Brooklyn segment envelope")
            if not -73.93 <= longitude <= -73.88:
                failures.append(f"longitude {longitude} is outside the certified Brooklyn segment envelope")

        if coordinate_status and str(coordinate_status).lower() != "map_ready":
            failures.append(f"coordinate status is {coordinate_status!r}, expected map_ready")

    return {
        "name": "Required Brooklyn block party 923896",
        "source_event_id": REQUIRED_EVENT_ID,
        "required_date": REQUIRED_EVENT_DATE,
        "approved_pages_scanned": len(page_files),
        "match_count": len(matches),
        "page": page_name,
        "event_id": event_id,
        "start": start_value,
        "borough": borough,
        "location": location_text,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_status": coordinate_status,
        "qa_pass": not failures,
        "failures": failures,
        "operating_rule": (
            "Event 923896 must appear exactly once in the approved public feed on 2026-08-01 "
            "with the East 74 Street / Avenue U / Avenue T Brooklyn segment pin."
        ),
    }


def refresh_field_desk_overlay_health() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_field_desk_overlay_health.py")],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    payload = load(FIELD_DESK_OVERLAY_HEALTH, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    if result.returncode != 0 and not payload:
        payload = {
            "qa_pass": False,
            "overlay_count": 0,
            "blockers": [
                {
                    "code": "overlay_health_process_failed",
                    "message": (result.stderr or result.stdout or "Field Desk overlay health process failed")[-2000:],
                }
            ],
        }
    payload["check_exit_code"] = result.returncode
    return payload


def main() -> int:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    sources = [
        source_status(
            "NYC permitted events",
            DATA / "live_sync_report.json",
            ("raw_rows_loaded", "source_rows"),
        ),
        source_status(
            "NYC Citywide Calendar",
            DATA / "nyc_citywide_events_calendar_sync_report.json",
            ("snapshot_rows", "rows", "source_rows", "event_count"),
        ),
        source_status(
            "NYC Parks BigApps",
            DATA / "nyc_parks_bigapps_events_sync_report.json",
            ("snapshot_rows", "rows", "source_rows", "event_count"),
            require_live_mode=True,
        ),
    ]

    staged = load(DATA / "staged_live_manifest.json", {}) or {}
    reconciliation = load(DATA / "events_discovery_reconciliation_v02.json", {}) or {}
    schema_validation = load(DATA / "events_discovery_schema_validation_v02.json", {}) or {}
    cems = load(
        DATA / "schema-v1-discovery" / "shared-cems-occurrence-dedupe-summary.json",
        {},
    ) or {}
    cross_source = load(DATA / "reports" / "discovery_approved_dedupe_report.json", {}) or {}
    runtime_fallback = load(DATA / "runtime_fallback_feed_report.json", {}) or {}
    photographer = load(DATA / "photographer_assignment_calendar_report.json", {}) or {}
    viral = load(DATA / "photographer_viral_recurrence_report.json", {}) or {}
    field_desk_overlay = refresh_field_desk_overlay_health()
    required_event = required_event_status()

    derived = [
        artifact_status("Map-ready staged feed", DATA / "staged_live_manifest.json", ("staged_feed_events",)),
        artifact_status(
            "Approved public discovery feed",
            DATA / "schema-v1-discovery" / "approved" / "manifest.json",
            ("total",),
        ),
        artifact_status(
            "Cross-source dedupe evidence",
            DATA / "reports" / "discovery_approved_dedupe_report.json",
            ("output_count",),
            require_qa=True,
        ),
        artifact_status(
            "Shared-CEMS dedupe evidence",
            DATA / "schema-v1-discovery" / "shared-cems-occurrence-dedupe-summary.json",
            ("output_count",),
            require_qa=True,
        ),
        artifact_status(
            "Emergency major fallback",
            DATA / "runtime_fallback_feed_report.json",
            ("output_event_count",),
            require_qa=True,
        ),
        artifact_status(
            "News Desk money-day calendar",
            DATA / "photographer_assignment_calendar_report.json",
            ("total_events",),
            require_qa=True,
        ),
        artifact_status(
            "News Desk viral recurrence overlay",
            DATA / "photographer_viral_recurrence_report.json",
            ("match_count",),
            require_qa=True,
        ),
    ]

    equations = reconciliation.get("equations") if isinstance(reconciliation, dict) else {}
    equations = equations if isinstance(equations, dict) else {}
    gap = int(equations.get("calendar_parks_unaccounted_gap") or 0)
    strict_reconciliation = bool(reconciliation.get("reconciles_strict")) and gap == 0
    canonical_ids_clean = bool(schema_validation.get("qa_pass")) and int(
        schema_validation.get("error_count") or 0
    ) == 0
    cems_clean = bool(cems.get("qa_pass")) and int(cems.get("fatal_blocked_group_count") or 0) == 0
    cross_source_clean = bool(cross_source.get("qa_pass"))
    runtime_fallback_clean = bool(runtime_fallback.get("qa_pass")) and int(
        runtime_fallback.get("duplicate_ids") or 0
    ) == 0
    photographer_clean = bool(photographer.get("qa_pass"))
    viral_clean = bool(viral.get("qa_pass"))
    field_desk_overlays_clean = (
        bool(field_desk_overlay.get("qa_pass"))
        and int(field_desk_overlay.get("overlay_count") or 0) == 3
        and int(field_desk_overlay.get("check_exit_code") or 0) == 0
    )
    required_event_clean = bool(required_event.get("qa_pass"))
    cross_date_suppressed = int(staged.get("cross_date_street_occurrences_suppressed") or 0)
    exact_occurrence_suppressed = int(staged.get("exact_occurrence_duplicates_suppressed") or 0)

    blockers: list[dict[str, str]] = []
    for source in sources:
        if not source["fresh"]:
            detail = source.get("error") or source.get("fetch_mode") or "missing/expired report"
            blockers.append(
                blocker(
                    "source_not_live_and_fresh",
                    f"{source['name']} is not a successful live fetch within {MAX_SOURCE_AGE_HOURS:g} hours ({detail}).",
                    source["artifact"],
                )
            )
    for item in derived:
        if not item["fresh"]:
            blockers.append(
                blocker(
                    "runtime_artifact_not_fresh_and_valid",
                    f"{item['name']} is missing, stale, or failed its generation QA.",
                    item["artifact"],
                )
            )
    if not strict_reconciliation:
        blockers.append(
            blocker(
                "strict_reconciliation_failed",
                f"Source accounting is not strict; Calendar/Parks unexplained gap is {gap}.",
                "data/events_discovery_reconciliation_v02.json",
            )
        )
    if not canonical_ids_clean:
        blockers.append(
            blocker(
                "canonical_identity_failed",
                "Canonical identity/schema validation did not pass with zero errors.",
                "data/events_discovery_schema_validation_v02.json",
            )
        )
    if not cross_source_clean:
        blockers.append(
            blocker(
                "cross_source_dedupe_failed",
                "Cross-source approved-feed dedupe did not pass in this generation.",
                "data/reports/discovery_approved_dedupe_report.json",
            )
        )
    if not cems_clean:
        blockers.append(
            blocker(
                "cems_dedupe_failed",
                "Shared-CEMS occurrence dedupe failed or contains fatal blocked groups.",
                "data/schema-v1-discovery/shared-cems-occurrence-dedupe-summary.json",
            )
        )
    if not runtime_fallback_clean:
        blockers.append(
            blocker(
                "runtime_fallback_failed",
                "The emergency major fallback was not rebuilt from the authoritative major feed.",
                "data/runtime_fallback_feed_report.json",
            )
        )
    if not photographer_clean or not viral_clean:
        blockers.append(
            blocker(
                "news_desk_overlay_failed",
                "The money-day or viral News Desk overlay did not rebuild successfully.",
                "data/photographer_assignment_calendar_report.json",
            )
        )
    if not field_desk_overlays_clean:
        details = field_desk_overlay.get("blockers") or []
        blockers.append(
            blocker(
                "field_desk_public_overlays_failed",
                "Nightlife, legal cannabis, or smoke/vape correlation is stale, count-misaligned, or contains duplicate public markers. "
                + json.dumps(details, ensure_ascii=False)[:1200],
                "nycif-field-desk/data/reports/",
            )
        )
    if not required_event_clean:
        blockers.append(
            blocker(
                "required_event_923896_failed",
                "Required event 923896 is missing, duplicated, assigned to the wrong date/location, or has a non-Brooklyn pin: "
                + json.dumps(required_event.get("failures") or [], ensure_ascii=False),
                "data/schema-v1-discovery/approved/pages/",
            )
        )
    if cross_date_suppressed:
        blockers.append(
            blocker(
                "cross_date_occurrence_loss",
                f"{cross_date_suppressed} legitimate dated street occurrences were suppressed across dates.",
                "data/staged_live_manifest.json",
            )
        )

    release_ready = not blockers
    payload = {
        "artifact_type": "nycif_daily_data_health",
        "schema_version": "1.4.0",
        "generated_at_utc": generated,
        "company_focus": "News Desk live-data completeness, freshness, and duplicate safety",
        "status": "READY" if release_ready else "BLOCKED",
        "release_ready": release_ready,
        "daily_refresh_required": True,
        "sources": sources,
        "derived_artifacts": derived,
        "runtime_feeds": {
            "primary_major": "data/schema-v1-discovery/major/events.json",
            "same-ref_fallback": "data/events_discovery_v02_major.json",
            "main_emergency": "nycif_major_radar_map_events.json",
            "approved_pages": "data/schema-v1-discovery/approved/",
            "review_pages": "data/schema-v1-discovery/review/",
            "newly_added_sort": "data/nycif_new_events.json",
            "money_overlay": "data/photographer_assignment_calendar_2mo.json",
            "viral_overlay": "data/photographer_viral_recurrence_matches.json",
            "active_nightlife_overlay": "nycif-field-desk/data/nycif_active_nightlife_feed.json",
            "legal_cannabis_overlay": "nycif-field-desk/data/nycif_legal_cannabis_dispensaries.json",
            "smoke_vape_correlation_overlay": "nycif-field-desk/data/nycif_smoke_vape_cannabis_correlation.json",
        },
        "field_desk_overlay_health": field_desk_overlay,
        "required_event_checks": {
            "event_923896": required_event,
        },
        "pipeline": {
            "strict_reconciliation": strict_reconciliation,
            "calendar_parks_unaccounted_gap": gap,
            "canonical_identity_clean": canonical_ids_clean,
            "cross_source_dedupe_clean": cross_source_clean,
            "shared_cems_dedupe_clean": cems_clean,
            "runtime_fallback_clean": runtime_fallback_clean,
            "photographer_money_day_clean": photographer_clean,
            "viral_recurrence_clean": viral_clean,
            "field_desk_public_overlays_clean": field_desk_overlays_clean,
            "required_event_923896_public_and_correct": required_event_clean,
            "exact_occurrence_duplicates_suppressed": exact_occurrence_suppressed,
            "cross_date_street_occurrences_suppressed": cross_date_suppressed,
        },
        "blockers": blockers,
        "operating_rule": "Do not commit or publish a refreshed public feed unless status is READY.",
        "rollback_rule": "A failed refresh leaves public feed JSON unchanged and publishes only a BLOCKED God View status.",
        "enigma": {
            "production_authority": False,
            "mode": "shadow_only",
            "note": "V1 remains the production authority until a separately governed real-data Enigma phase is authorized.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if release_ready else 1


if __name__ == "__main__":
    sys.exit(main())
