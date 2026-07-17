#!/usr/bin/env python3
"""Copy supplemental approved export feed to dist/ for field-desk CI preview.

Does NOT modify location_cache.json, permit staged feed, or public map feeds.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        ROOT,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        ROOT,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
    )

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
DIST_DIR = ROOT / "dist"
DIST_EXPORT_PATH = DIST_DIR / "supplemental_approved_export_feed.json"
DIST_MAP_PINS_PATH = DIST_DIR / "supplemental_approved_export_map_pins.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_approved_export_publish_report.json"

FIELD_DESK_RAW_URL = (
    "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/"
    "dist/supplemental_approved_export_feed.json"
)
FIELD_DESK_MAP_PINS_URL = (
    "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/"
    "dist/supplemental_approved_export_map_pins.json"
)
FIELD_DESK_BACKEND_DATA_URL = (
    "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/"
    "data/supplemental_approved_export_feed.json"
)


def validate_export_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("export feed must be a JSON object")
    if payload.get("artifact_type") != "supplemental_approved_export_feed":
        raise ValueError(
            f"refusing artifact_type={payload.get('artifact_type')!r}; "
            "expected supplemental_approved_export_feed"
        )
    if payload.get("production_feed") is True:
        raise ValueError("refusing production_feed=true artifact for preview publish")
    if payload.get("promotion_allowed") is True:
        raise ValueError("refusing promotion_allowed=true artifact for preview publish")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("export feed missing events array")
    return payload


def lite_pin_from_event(row: dict[str, Any], index: int) -> dict[str, Any]:
    lat = row.get("lat", row.get("proposed_lat"))
    lng = row.get("lng", row.get("proposed_lng"))
    return {
        "id": row.get("overlap_key") or row.get("source_event_id") or f"supplemental-export-{index}",
        "lat": lat,
        "lng": lng,
        "title": row.get("title") or "Supplemental approved event",
        "displayLocation": row.get("display_location") or "",
        "borough": row.get("borough") or "",
        "date": row.get("date") or "",
        "geocoderSource": row.get("geocoder_source") or "",
        "geocoderConfidence": row.get("geocoder_confidence") or "",
    }


def build_map_pins_payload(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("events") or []
    pins = [lite_pin_from_event(row, index) for index, row in enumerate(events)]
    return {
        "artifact_type": "supplemental_approved_export_map_pins",
        "generated_at_utc": payload.get("generated_at_utc"),
        "export_event_count": len(pins),
        "approved_queue_count": payload.get("approved_queue_count"),
        "production_feed": False,
        "promotion_allowed": False,
        "pins": pins,
    }


def publish_export_feed() -> dict[str, Any]:
    payload = validate_export_payload(load_json_file(EXPORT_PATH, {}))
    if not EXPORT_PATH.exists():
        raise FileNotFoundError(f"missing source export feed: {repo_relative(EXPORT_PATH)}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXPORT_PATH, DIST_EXPORT_PATH)
    map_pins = build_map_pins_payload(payload)
    save_json_file(DIST_MAP_PINS_PATH, map_pins)

    generated_at = utc_now_iso()
    report = {
        "artifact_type": "supplemental_approved_export_publish_report",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_approved_export_publish",
        "qa_pass": True,
        "source_path": repo_relative(EXPORT_PATH),
        "published_path": repo_relative(DIST_EXPORT_PATH),
        "map_pins_path": repo_relative(DIST_MAP_PINS_PATH),
        "map_pin_count": map_pins.get("export_event_count"),
        "export_event_count": payload.get("export_event_count"),
        "approved_queue_count": payload.get("approved_queue_count"),
        "field_desk_urls": {
            "dist_raw": FIELD_DESK_RAW_URL,
            "map_pins_raw": FIELD_DESK_MAP_PINS_URL,
            "backend_data_raw": FIELD_DESK_BACKEND_DATA_URL,
        },
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Field-desk preview only. Use approved-export-preview.html or "
            "desk.html?previewExport=1. Public map merge requires explicit Phase 2E authorization."
        ),
    }
    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    try:
        report = publish_export_feed()
    except (FileNotFoundError, ValueError) as exc:
        report = {
            "artifact_type": "supplemental_approved_export_publish_report",
            "generated_at_utc": utc_now_iso(),
            "phase": "m11_supplemental_approved_export_publish",
            "qa_pass": False,
            "error": str(exc),
            "source_path": repo_relative(EXPORT_PATH),
            "published_path": repo_relative(DIST_EXPORT_PATH),
        }
        save_json_file(REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
