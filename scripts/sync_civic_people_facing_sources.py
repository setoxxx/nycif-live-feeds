#!/usr/bin/env python3
"""Fetch official NYC Open Data SODA JSON snapshots for people-facing civic intake.

Staging only. Does not modify location_cache or production staged feeds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import (  # noqa: E402
    DATA_DIR,
    SOURCE_CATALOG,
    fetch_soda_rows,
    save_json,
    utc_now,
)


def sync_one(key: str, meta: dict[str, Any]) -> dict[str, Any]:
    dataset = meta["dataset"]
    generated = utc_now()
    error = None
    rows: list[dict[str, Any]] = []
    try:
        rows = fetch_soda_rows(dataset)
    except Exception as exc:  # noqa: BLE001 - sync report must capture fetch failures
        error = str(exc)

    nonempty = [r for r in rows if any(str(v).strip() for v in r.values())]
    empty_payload_count = len(rows) - len(nonempty)
    # Socrata occasionally pads large offsets with {} — store only usable rows.
    stored_rows = nonempty

    snapshot = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": generated,
        "source_key": key,
        "dataset": dataset,
        "portal": meta["portal"],
        "soda_endpoint": f"https://data.cityofnewyork.us/resource/{dataset}.json",
        "lane": meta["lane"],
        "row_count": len(stored_rows),
        "fetched_row_count": len(rows),
        "nonempty_row_count": len(nonempty),
        "empty_payload_row_count": empty_payload_count,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": meta.get("notes"),
        "rows": stored_rows,
    }
    snapshot_path = DATA_DIR / meta["snapshot"]
    save_json(snapshot_path, snapshot)

    report = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": generated,
        "source_key": key,
        "dataset": dataset,
        "portal": meta["portal"],
        "soda_endpoint": snapshot["soda_endpoint"],
        "lane": meta["lane"],
        "snapshot_path": f"data/{meta['snapshot']}",
        "qa_pass": error is None and (len(nonempty) > 0 or key == "workforce1_jobs"),
        "fetch_error": error,
        "row_count": len(stored_rows),
        "fetched_row_count": len(rows),
        "nonempty_row_count": len(nonempty),
        "empty_payload_row_count": empty_payload_count,
        "optional": bool(meta.get("optional")),
        "notes": meta.get("notes"),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "sample_keys": sorted({k for r in nonempty[:5] for k in r.keys()}),
    }
    # workforce1_jobs: SODA returns empty objects — treated as known API gap, sync still "passes" with warning
    if key == "workforce1_jobs":
        report["qa_pass"] = error is None
        report["warning"] = (
            "SODA endpoint returns empty objects despite metadata column list; "
            "jobs listing cannot be staged until fields are present in the public API."
        )
    save_json(DATA_DIR / meta["report"], report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="*",
        help="Optional source keys to sync (default: all catalog entries)",
    )
    args = parser.parse_args()
    keys = args.only or list(SOURCE_CATALOG.keys())
    reports = []
    for key in keys:
        if key not in SOURCE_CATALOG:
            print(f"unknown source key: {key}", file=sys.stderr)
            return 2
        print(f"syncing {key}…")
        report = sync_one(key, SOURCE_CATALOG[key])
        reports.append(report)
        status = "PASS" if report["qa_pass"] else "FAIL"
        print(f"  {status} rows={report['row_count']} nonempty={report['nonempty_row_count']}")

    summary = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "source_count": len(reports),
        "qa_pass": all(r["qa_pass"] for r in reports if not r.get("optional")),
        "reports": [
            {
                "source_key": r["source_key"],
                "dataset": r["dataset"],
                "qa_pass": r["qa_pass"],
                "row_count": r["row_count"],
                "nonempty_row_count": r["nonempty_row_count"],
                "snapshot_path": r["snapshot_path"],
            }
            for r in reports
        ],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    save_json(DATA_DIR / "civic_people_facing_sync_summary.json", summary)
    print(f"summary qa_pass={summary['qa_pass']}")
    return 0 if summary["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
