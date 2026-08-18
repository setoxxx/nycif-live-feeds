#!/usr/bin/env python3
"""NYCIF Supabase event writer (dry-run only).

No database writes are performed.
This module compares canonical Enigma output against a supplied Supabase
read-only snapshot.
"""

from __future__ import annotations

import argparse
import json
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


def extract_events(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("events", [])
    return []


def load_supabase_snapshot(path: Path | None):
    """Read-only adapter boundary.

    Future Supabase API/database connector code belongs here.
    This function intentionally only reads exported state.
    """
    if not path:
        return {
            "occurrences": {},
            "sources": {},
            "classifications": {},
            "quality": {},
        }
    return load_json(path)


def occurrence_key(event):
    return str(event.get("id") or event.get("occurrence_id") or "")


def compare_to_supabase(canonical_events, supabase_state):
    existing = supabase_state.get("occurrences", {})

    report = {
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
            "missing_quality_rows": 0,
        },
        "location": {
            "coordinate_changes": 0,
            "map_state_changes": 0,
        },
    }

    seen = set()
    for event in canonical_events:
        key = occurrence_key(event)
        if not key:
            report["identity"]["missing_ids"] += 1
            continue
        if key in seen:
            report["identity"]["duplicate_ids"] += 1
            continue
        seen.add(key)
        report["actions"]["UPDATE" if key in existing else "INSERT"] += 1

    for key in existing:
        if key not in seen:
            report["actions"]["EXPIRE"] += 1

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--supabase-snapshot")
    args = parser.parse_args()

    canonical = extract_events(load_json(Path(args.input)))
    supabase = load_supabase_snapshot(
        Path(args.supabase_snapshot) if args.supabase_snapshot else None
    )

    report = {
        "run_type": "dry_run",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_count": len(canonical),
        **compare_to_supabase(canonical, supabase),
        "database_write_performed": False,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
