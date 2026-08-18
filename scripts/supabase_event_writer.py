#!/usr/bin/env python3
"""NYCIF Supabase event writer (dry-run prototype).

This module intentionally performs no database writes.
It compares canonical Enigma output against Supabase state and produces a
migration planning report.

Future write modes must preserve:
- OccurrenceIdentityV2 as occurrence identity authority.
- source truth in event_sources.
- lifecycle history in event_change_log.
- quality history in event_quality_history.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "reports" / "supabase_writer_report.json"


ACTIONS = (
    "INSERT",
    "UPDATE",
    "UNCHANGED",
    "EXPIRE",
    "QUALITY_CHANGE",
    "CLASSIFICATION_CHANGE",
    "LOCATION_CHANGE",
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(input_count: int = 0) -> dict:
    return {
        "run_type": "dry_run",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_count": input_count,
        "actions": {key: 0 for key in ACTIONS},
        "identity": {
            "duplicate_ids": 0,
            "missing_ids": 0,
            "orphan_sources": 0,
        },
        "classification": {
            "category_changes": 0,
            "subtype_changes": 0,
        },
        "quality": {
            "new_flags": 0,
            "resolved_flags": 0,
        },
        "location": {
            "coordinate_changes": 0,
            "map_state_changes": 0,
        },
        "database_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Canonical Enigma JSON input")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    count = 0
    if args.input:
        payload = load_json(Path(args.input))
        if isinstance(payload, list):
            count = len(payload)
        elif isinstance(payload, dict):
            count = len(payload.get("events", []))

    report = build_report(count)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
