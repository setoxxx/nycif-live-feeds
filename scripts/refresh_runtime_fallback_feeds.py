#!/usr/bin/env python3
"""Refresh every map runtime fallback from the current authoritative build.

The public map's emergency URL is a legacy root-level JSON array. Rebuild it
from the same schema-v1 major feed generated in the daily transaction so a
primary-feed outage cannot resurrect stale June data.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "schema-v1-discovery" / "major" / "events.json"
OUTPUT = ROOT / "nycif_major_radar_map_events.json"
REPORT = ROOT / "data" / "runtime_fallback_feed_report.json"


def events(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def main() -> int:
    generated = datetime.now(timezone.utc).isoformat()
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = events(payload)
    ids = [str(row.get("id") or "") for row in rows]
    duplicate_ids = len(ids) - len(set(ids))
    qa_pass = bool(rows) and duplicate_ids == 0 and all(ids)

    if qa_pass:
        OUTPUT.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    report = {
        "artifact_type": "nycif_runtime_fallback_feed_report",
        "generated_at_utc": generated,
        "qa_pass": qa_pass,
        "source": str(SOURCE.relative_to(ROOT)),
        "output": str(OUTPUT.relative_to(ROOT)),
        "source_event_count": len(rows),
        "output_event_count": len(rows) if qa_pass else 0,
        "duplicate_ids": duplicate_ids,
        "stale_legacy_rows_replaced": qa_pass,
        "operating_rule": "Emergency map fallback must be regenerated from the same authoritative major feed in every READY transaction.",
    }
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
