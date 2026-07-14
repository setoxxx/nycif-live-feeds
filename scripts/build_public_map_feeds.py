#!/usr/bin/env python3
"""Refresh public map feed JSON from the GPS-ready test enriched pipeline.

Writes production-shaped feeds consumed by nycif-field-desk and WordPress.
Does not modify location_cache.json or GPS review artifacts.

Inputs:
- data/nycif_live_test_enriched_events.json

Outputs:
- nycif_all_radar_map_events.json (full GPS-ready permit events)
- feed-metadata.json
- data/public_map_feed_publish_report.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TEST_FEED = DATA / "nycif_live_test_enriched_events.json"
ALL_FEED = ROOT / "nycif_all_radar_map_events.json"
METADATA = ROOT / "feed-metadata.json"
REPORT = DATA / "public_map_feed_publish_report.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_test(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def valid_gps(row: dict[str, Any]) -> bool:
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def public_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "category": row.get("category") or "general",
        "borough": row.get("borough"),
        "location": row.get("location") or row.get("display_location"),
        "display_location": row.get("display_location") or row.get("location"),
        "lat": float(row.get("lat")),
        "lng": float(row.get("lng")),
        "date": row.get("date"),
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "display_time": row.get("display_time"),
        "event_agency": row.get("event_agency"),
        "event_type": row.get("event_type"),
        "street_closure_type": row.get("street_closure_type"),
        "source_dataset": row.get("source_dataset") or "tvpp-9vvx",
        "source_event_id": row.get("source_event_id"),
        "match_type": row.get("match_type"),
        "location_source": row.get("location_source") or row.get("match_type"),
        "production_feed": True,
    }


def main() -> int:
    test_payload = load_json(TEST_FEED, {})
    rows = rows_from_test(test_payload)
    gps_ready = [row for row in rows if row.get("needs_review") is False and valid_gps(row)]
    events = [public_event(row) for row in gps_ready]
    events.sort(key=lambda row: (row.get("date") or "9999-99-99", row.get("start_date_time") or "", row.get("title") or ""))

    generated_at = datetime.now(timezone.utc).isoformat()
    feed = {
        "generated_at_utc": generated_at,
        "source": "nycif_live_test_enriched_events.json",
        "resolver_pipeline": "tiered_gazetteer_geosearch_m9_m10",
        "production_feed": True,
        "events": events,
    }
    metadata = {
        "generated_at_utc": generated_at,
        "feed_name": "nycif_all_radar_map_events",
        "event_count": len(events),
        "source_test_feed": "data/nycif_live_test_enriched_events.json",
        "staged_feed_companion": "data/nycif_staged_live_events.json",
        "public_map_urls": {
            "github_pages_map": "https://setoxxx.github.io/nycif-field-desk/",
            "wordpress_map": "https://nycinfocus.com/map/",
            "all_feed_raw": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json",
            "staged_feed_raw": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json",
        },
    }
    report = {
        "generated_at_utc": generated_at,
        "phase": "public_map_feed_refresh",
        "qa_pass": len(events) > 0,
        "test_feed_rows": len(rows),
        "gps_ready_events": len(events),
        "needs_review_skipped": len(rows) - len(events),
        "outputs": {
            "all_feed": str(ALL_FEED.relative_to(ROOT)),
            "metadata": str(METADATA.relative_to(ROOT)),
        },
        "location_cache_modified": False,
        "public_map_modified": False,
        "note": "Frontend/WordPress must be deployed separately to consume refreshed feeds.",
    }

    save_json(ALL_FEED, feed)
    save_json(METADATA, metadata)
    save_json(REPORT, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
