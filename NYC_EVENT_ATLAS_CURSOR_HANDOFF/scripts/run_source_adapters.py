#!/usr/bin/env python3
"""Run Atlas source adapters 1–8 into the review queue (no silent EVENT_ID growth)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from nyc_event_atlas.adapters import ADAPTERS

ROOT = Path(__file__).resolve().parents[1]

ORDER = [
    "parks",
    "public_calendar",
    "clearview",
    "nyc_street_fairs",
    "community",
    "holidays",
    "santa_rosalia",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help=f"Subset of adapters: {', '.join(ORDER)}",
    )
    parser.add_argument(
        "--parks-snapshot",
        default=None,
        help="Optional offline Parks BigApps JSON snapshot path",
    )
    parser.add_argument(
        "--calendar-snapshot",
        default=None,
        help="Optional offline citywide calendar JSON snapshot path",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    selected = args.only or ORDER
    for name in selected:
        if name not in ADAPTERS:
            raise SystemExit(f"Unknown adapter {name!r}. Choose from {ORDER}")

    db = ROOT / "data" / "atlas.sqlite"
    if not db.exists():
        raise SystemExit("Missing data/atlas.sqlite — run bootstrap_db.py + import_existing.py first")

    reports = {}
    with sqlite3.connect(db) as conn:
        for name in selected:
            fn = ADAPTERS[name]
            kwargs = {"window_start": start, "window_end": end}
            if name == "parks" and args.parks_snapshot:
                kwargs["offline_snapshot"] = Path(args.parks_snapshot)
            if name == "public_calendar" and args.calendar_snapshot:
                kwargs["offline_snapshot"] = Path(args.calendar_snapshot)
            print(f"== adapter: {name}", flush=True)
            try:
                reports[name] = fn(conn, **kwargs)
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                reports[name] = {"error": str(exc), "mapped_rows": 0}
            print(json.dumps(reports[name], indent=2, default=str)[:1200], flush=True)

    out = ROOT / "data" / "staging" / "source_adapters_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "window": {"start": args.start, "end": args.end},
        "adapters": reports,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
