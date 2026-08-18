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


def extract_events(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("events", [])
    return []


def occurrence_key(event):
    return str(event.get("id") or event.get("occurrence_id") or "")


def compare_to_supabase(canonical_events, supabase_state=None):
    """Read-only comparison contract.

    A future adapter will populate supabase_state. This function never writes.
    """
    supabase_state = supabase_state or {}
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


def build_report(input_count: int = 0, comparison=None) -> dict:
    return {
        "run_type": "dry_run",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_count": input_count,
        **(comparison or compare_to_supabase([])),
        "database_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Canonical Enigma JSON input")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    events = []
    if args.input:
        events = extract_events(load_json(Path(args.input)))

    report = build_report(len(events), compare_to_supabase(events))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
