#!/usr/bin/env python3
"""Verify every auxiliary JSON feed loaded by the public map.

The event pipeline and public overlay pipeline live in separate repositories.
This gate verifies the three exact overlay arrays served by Field Desk main and
the local ``nycif_new_events.json`` consumed by the Newly added sort. It checks
freshness, count alignment, schema, unique IDs, and unique semantic marker
identities, then writes one God View health artifact.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "status" / "nycif-field-desk-overlay-health.json"
NEWLY_ADDED_PATH = ROOT / "data" / "nycif_new_events.json"
BASE = "https://raw.githubusercontent.com/setoxxx/nycif-field-desk/main"
MAX_AGE_HOURS = 36.0

CONFIGS = [
    {
        "name": "Active nightlife / 5PM",
        "data": "data/nycif_active_nightlife_feed.json",
        "report": "data/reports/active_nightlife_feed_report.json",
        "count_key": "feed_records",
    },
    {
        "name": "Legal cannabis dispensaries",
        "data": "data/nycif_legal_cannabis_dispensaries.json",
        "report": "data/reports/legal_cannabis_dispensaries_report.json",
        "count_key": "mapped_total",
    },
    {
        "name": "Smoke/vape/cannabis correlation",
        "data": "data/nycif_smoke_vape_cannabis_correlation.json",
        "report": "data/reports/smoke_vape_cannabis_correlation_report.json",
        "count_key": "output_locations",
        "require_qa": True,
    },
]


def fetch_json(path: str) -> Any:
    request = urllib.request.Request(
        f"{BASE}/{path}",
        headers={"Accept": "application/json", "User-Agent": "NYCIF-daily-data-health/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def load_local_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def marker_key(row: dict[str, Any]) -> str:
    try:
        lat = f"{float(row.get('lat')):.5f}"
        lng = f"{float(row.get('lng')):.5f}"
    except (TypeError, ValueError):
        lat = ""
        lng = ""
    return "|".join(
        [
            normalized(row.get("location_kind")),
            normalized(row.get("title") or row.get("dba_name") or row.get("legal_name")),
            normalized(row.get("address")),
            lat,
            lng,
        ]
    )


def row_id(row: dict[str, Any]) -> str:
    return str(
        row.get("id")
        or row.get("raw_source_id")
        or row.get("license_number")
        or row.get("ocm_license_number")
        or ""
    ).strip()


def newly_added_status(now: datetime) -> dict[str, Any]:
    payload = load_local_json(NEWLY_ADDED_PATH)
    if not isinstance(payload, dict):
        return {
            "name": "Newly added event-list sort",
            "artifact": str(NEWLY_ADDED_PATH.relative_to(ROOT)),
            "qa_pass": False,
            "error": "missing, empty, or invalid JSON object",
        }

    generated_value = payload.get("generated_at_utc") or payload.get("generated_at")
    generated_at = parse_time(generated_value)
    age_hours = round((now - generated_at).total_seconds() / 3600, 2) if generated_at else None
    fresh = age_hours is not None and 0 <= age_hours <= MAX_AGE_HOURS
    events = payload.get("events")
    events = events if isinstance(events, list) else []
    ids = [row_id(row) for row in events if isinstance(row, dict)]
    missing_ids = len(events) - len([value for value in ids if value])
    duplicate_ids = len([value for value in ids if value]) - len(set(value for value in ids if value))
    try:
        new_this_run = int(payload.get("new_this_run"))
        total_tracked = int(payload.get("total_tracked"))
        counts_valid = new_this_run >= 0 and total_tracked >= 0 and new_this_run == len(events)
    except (TypeError, ValueError):
        new_this_run = None
        total_tracked = None
        counts_valid = False

    qa_pass = fresh and counts_valid and missing_ids == 0 and duplicate_ids == 0
    return {
        "name": "Newly added event-list sort",
        "artifact": str(NEWLY_ADDED_PATH.relative_to(ROOT)),
        "generated_at_utc": generated_value,
        "age_hours": age_hours,
        "max_age_hours": MAX_AGE_HOURS,
        "fresh": fresh,
        "new_this_run": new_this_run,
        "event_count": len(events),
        "total_tracked": total_tracked,
        "counts_valid": counts_valid,
        "missing_ids": missing_ids,
        "duplicate_ids": duplicate_ids,
        "qa_pass": qa_pass,
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    generated = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    for config in CONFIGS:
        try:
            rows = fetch_json(config["data"])
            report = fetch_json(config["report"])
        except Exception as exc:
            item = {
                "name": config["name"],
                "data_artifact": config["data"],
                "report_artifact": config["report"],
                "qa_pass": False,
                "error": str(exc),
            }
            results.append(item)
            blockers.append({"code": "overlay_fetch_failed", "message": f"{config['name']}: {exc}"})
            continue

        if not isinstance(rows, list):
            rows = []
        if not isinstance(report, dict):
            report = {}

        report_time_value = report.get("generated_at_utc") or report.get("generated_at")
        report_time = parse_time(report_time_value)
        age_hours = round((now - report_time).total_seconds() / 3600, 2) if report_time else None
        fresh = age_hours is not None and 0 <= age_hours <= MAX_AGE_HOURS
        expected_count = int(report.get(config["count_key"]) or 0)
        count_aligned = expected_count == len(rows) and len(rows) > 0

        ids = [row_id(row) for row in rows]
        missing_ids = sum(1 for value in ids if not value)
        duplicate_ids = len([value for value in ids if value]) - len(set(value for value in ids if value))
        keys = [marker_key(row) for row in rows]
        duplicate_semantic_markers = len(keys) - len(set(keys))
        report_qa = bool(report.get("qa_pass", True))
        qa_pass = (
            fresh
            and count_aligned
            and missing_ids == 0
            and duplicate_ids == 0
            and duplicate_semantic_markers == 0
            and (report_qa or not config.get("require_qa"))
        )

        item = {
            "name": config["name"],
            "data_artifact": config["data"],
            "report_artifact": config["report"],
            "report_generated_at_utc": report_time_value,
            "age_hours": age_hours,
            "max_age_hours": MAX_AGE_HOURS,
            "row_count": len(rows),
            "reported_count": expected_count,
            "count_aligned": count_aligned,
            "missing_ids": missing_ids,
            "duplicate_ids": duplicate_ids,
            "duplicate_semantic_public_markers": duplicate_semantic_markers,
            "report_qa_pass": report_qa,
            "qa_pass": qa_pass,
        }
        results.append(item)
        if not qa_pass:
            blockers.append(
                {
                    "code": "overlay_not_fresh_valid_duplicate_clean",
                    "message": (
                        f"{config['name']} failed: fresh={fresh}, count_aligned={count_aligned}, "
                        f"missing_ids={missing_ids}, duplicate_ids={duplicate_ids}, "
                        f"duplicate_markers={duplicate_semantic_markers}, report_qa={report_qa}."
                    ),
                    "artifact": config["report"],
                }
            )

    newly_added = newly_added_status(now)
    if not newly_added.get("qa_pass"):
        blockers.append(
            {
                "code": "newly_added_feed_not_fresh_valid_unique",
                "message": (
                    "Newly added sort feed failed freshness/schema/identity checks: "
                    + json.dumps(newly_added, ensure_ascii=False)[:1200]
                ),
                "artifact": str(NEWLY_ADDED_PATH.relative_to(ROOT)),
            }
        )

    qa_pass = len(results) == len(CONFIGS) and not blockers
    payload = {
        "artifact_type": "nycif_auxiliary_runtime_health",
        "schema_version": "1.1.0",
        "generated_at_utc": generated,
        "qa_pass": qa_pass,
        "repository": "setoxxx/nycif-field-desk",
        "branch": "main",
        "max_age_hours": MAX_AGE_HOURS,
        "overlay_count": len(results),
        "overlays": results,
        "local_runtime_checks": {
            "newly_added_sort": newly_added,
        },
        "blockers": blockers,
        "operating_rule": (
            "All auxiliary map overlays and the Newly added sort feed must be fresh, "
            "count-aligned, schema-valid, and duplicate-clean before the News Desk runtime is READY."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
