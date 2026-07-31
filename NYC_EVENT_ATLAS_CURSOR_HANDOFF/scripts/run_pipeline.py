#!/usr/bin/env python3
"""Permit-first pipeline orchestrator (fail-closed on validation).

Order:
  fetch permits -> ingest/dedupe/review -> export from SQLite -> validate

Does not invent dates/coords/organizers. Does not overwrite baseline EVENT_IDs.
Export runs only after ingest report is written; validation must pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    started = datetime.now(timezone.utc).isoformat()

    if not args.skip_fetch:
        run([py, "scripts/fetch_permits.py", "--start", args.start, "--end", args.end])
    # Conservative default: queue new permits for review; do not expand canonical
    # events until human verification (pass --auto-accept-new to ingest only if explicit).
    run([py, "scripts/ingest_permit_candidates.py"])
    run([py, "scripts/export_from_db.py", "--out", "data/exports"])
    cumulative = ROOT / "data" / "exports" / "NYC_EVENTS_MASTER_CUMULATIVE.csv"
    run([py, "scripts/validate_exports.py", str(cumulative)])

    manifest = {
        "started_at_utc": started,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "window": {"start": args.start, "end": args.end},
        "cumulative_export": str(cumulative),
        "ingest_report": "data/staging/permit_ingest_report.json",
        "status": "ok",
        "notes": "Coordinates left Unknown unless present in canonical baseline; permit importer does not geocode.",
    }
    path = ROOT / "logs" / "pipeline_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"pipeline ok -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
