#!/usr/bin/env python3
"""Build the launch-blocking daily data health contract for God View.

The report distinguishes a freshly regenerated wrapper from genuinely fresh,
successfully fetched source data. Every JSON family loaded by the public map or
News Desk overlays is included. The daily production workflow must stop before
committing public feed artifacts unless this script returns success.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATUS = ROOT / "status"
OUT = STATUS / "nycif-daily-data-health.json"
MAX_SOURCE_AGE_HOURS = 36.0


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
        "schema_version": "1.2.0",
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
            "money_overlay": "data/photographer_assignment_calendar_2mo.json",
            "viral_overlay": "data/photographer_viral_recurrence_matches.json",
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
