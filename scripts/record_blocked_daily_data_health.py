#!/usr/bin/env python3
"""Write a BLOCKED daily-data health artifact after a failed refresh.

This script is used only after the workflow resets the working tree to current
main, so it cannot publish partial feeds. It preserves the last-known-good data
and gives God View an exact failed stage, exit code, and rollback commit.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "status" / "nycif-daily-data-health.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--line", default="unknown")
    parser.add_argument("--previous-commit", required=True)
    args = parser.parse_args()

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    message = (
        f"Daily production refresh failed at stage '{args.stage}' "
        f"(exit {args.exit_code}, shell line {args.line}). Public feeds were not committed."
    )
    payload = {
        "artifact_type": "nycif_daily_data_health",
        "schema_version": "1.2.0",
        "generated_at_utc": generated,
        "company_focus": "News Desk live-data completeness, freshness, and duplicate safety",
        "status": "BLOCKED",
        "release_ready": False,
        "daily_refresh_required": True,
        "sources": [],
        "derived_artifacts": [],
        "pipeline": {
            "strict_reconciliation": False,
            "canonical_identity_clean": False,
            "cross_source_dedupe_clean": False,
            "shared_cems_dedupe_clean": False,
        },
        "blockers": [
            {
                "code": "daily_refresh_stage_failed",
                "severity": "critical",
                "message": message,
                "artifact": ".github/workflows/discovery-feed-refresh.yml",
                "stage": args.stage,
                "exit_code": args.exit_code,
                "line": args.line,
            }
        ],
        "operating_rule": "Do not commit or publish a refreshed public feed unless status is READY.",
        "rollback_rule": "The failed transaction was discarded; the previous serving commit remains authoritative.",
        "rollback": {
            "previous_public_feed_commit": args.previous_commit,
            "strategy": "No feed rollback was required because the failed transaction never committed.",
        },
        "enigma": {
            "production_authority": False,
            "mode": "shadow_only",
            "note": "V1 remains the sole production authority.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
