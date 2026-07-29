#!/usr/bin/env python3
"""Deterministic tests for Field Desk auxiliary overlay health."""

from __future__ import annotations

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


def run_case(*, duplicate: bool) -> int:
    now = datetime.now(timezone.utc).isoformat()
    payloads = {}
    for config in health.CONFIGS:
        rows = [row(f"{config['count_key']}-1", "One")]
        if duplicate:
            rows.append(row(f"{config['count_key']}-2", "ONE", lat=40.7000001, lng=-73.9000001))
        payloads[config["data"]] = rows
        payloads[config["report"]] = {
            "generated_at": now,
            "qa_pass": True,
            config["count_key"]: len(rows),
        }

    original_fetch = health.fetch_json
    original_out = health.OUT
    try:
        health.fetch_json = lambda path: payloads[path]
        with tempfile.TemporaryDirectory() as directory:
            health.OUT = Path(directory) / "overlay-health.json"
            return health.main()
    finally:
        health.fetch_json = original_fetch
        health.OUT = original_out


def main() -> int:
    assert run_case(duplicate=False) == 0
    assert run_case(duplicate=True) == 1
    print("PASS Field Desk overlay health accepts unique markers and blocks semantic duplicates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
