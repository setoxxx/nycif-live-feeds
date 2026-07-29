#!/usr/bin/env python3
"""Deterministic tests for auxiliary public-map runtime health."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_field_desk_overlay_health as health  # noqa: E402


def row(identifier: str, title: str, *, lat: float = 40.7, lng: float = -73.9) -> dict:
    return {
        "id": identifier,
        "title": title,
        "address": "1 Main Street, New York, NY",
        "lat": lat,
        "lng": lng,
        "location_kind": "test",
    }


def newly_added_payload(*, duplicate: bool = False, stale: bool = False) -> dict:
    generated = "2020-01-01T00:00:00Z" if stale else datetime.now(timezone.utc).isoformat()
    events = [
        {
            "id": "tvpp-9vvx:923896@2026-08-01",
            "title": "Block Party",
            "date": "2026-08-01",
            "first_seen_utc": generated,
        }
    ]
    if duplicate:
        events.append(dict(events[0]))
    return {
        "generated_at_utc": generated,
        "total_tracked": 100,
        "new_this_run": len(events),
        "events": events,
    }


def run_case(*, duplicate_overlay: bool = False, duplicate_new: bool = False, stale_new: bool = False) -> int:
    now = datetime.now(timezone.utc).isoformat()
    payloads = {}
    for config in health.CONFIGS:
        rows = [row(f"{config['count_key']}-1", "One")]
        if duplicate_overlay:
            rows.append(row(f"{config['count_key']}-2", "ONE", lat=40.7000001, lng=-73.9000001))
        payloads[config["data"]] = rows
        payloads[config["report"]] = {
            "generated_at": now,
            "qa_pass": True,
            config["count_key"]: len(rows),
        }

    original_fetch = health.fetch_json
    original_out = health.OUT
    original_new = health.NEWLY_ADDED_PATH
    try:
        health.fetch_json = lambda path: payloads[path]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory_path = Path(directory)
            health.OUT = directory_path / "overlay-health.json"
            health.NEWLY_ADDED_PATH = directory_path / "nycif_new_events.json"
            health.NEWLY_ADDED_PATH.write_text(
                json.dumps(newly_added_payload(duplicate=duplicate_new, stale=stale_new)),
                encoding="utf-8",
            )
            return health.main()
    finally:
        health.fetch_json = original_fetch
        health.OUT = original_out
        health.NEWLY_ADDED_PATH = original_new


def main() -> int:
    assert run_case() == 0
    assert run_case(duplicate_overlay=True) == 1
    assert run_case(duplicate_new=True) == 1
    assert run_case(stale_new=True) == 1
    print("PASS auxiliary health accepts fresh unique runtime feeds and blocks overlay/new-sort defects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
