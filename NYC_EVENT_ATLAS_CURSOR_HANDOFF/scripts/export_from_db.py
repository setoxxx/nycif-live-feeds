#!/usr/bin/env python3
"""Export canonical events from SQLite to the exact 59-column cumulative CSV (+ companions)."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from nyc_event_atlas.export import export_csv, export_geojson, export_kml, export_txt
from nyc_event_atlas.schema import EXPORT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/exports")
    args = parser.parse_args()

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(ROOT / "data" / "atlas.sqlite") as conn:
        rows = []
        for (record_json,) in conn.execute("SELECT record_json FROM events ORDER BY event_id"):
            rec = json.loads(record_json)
            rows.append({c: rec.get(c, "Unknown") for c in EXPORT_COLUMNS})

    # Stable sort: START_DATE then EVENT_ID
    rows.sort(key=lambda r: (r.get("START_DATE") or "", r.get("EVENT_ID") or ""))

    base = out / "NYC_EVENTS_MASTER_CUMULATIVE"
    export_csv(rows, str(base) + ".csv")
    export_txt(rows, str(base) + ".txt")
    export_geojson(rows, str(base) + ".geojson")
    export_kml(rows, str(base) + ".kml")

    # Part file = newly accepted rows from review apply (or legacy permit ingest report).
    part_rows = []
    accepted_ids: set[str] = set()
    for path_name in (
        "data/staging/accepted_event_ids.json",
        "data/staging/permit_ingest_report.json",
        "data/staging/review_apply_report.json",
    ):
        path = ROOT / path_name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        ids = payload.get("accepted_event_ids") or []
        accepted_ids.update(ids)
    if accepted_ids:
        part_rows = [r for r in rows if r["EVENT_ID"] in accepted_ids]
        part_base = out / "NYC_EVENTS_PART_013"
        export_csv(part_rows, str(part_base) + ".csv")
        export_txt(part_rows, str(part_base) + ".txt")
        print(f"part export: {len(part_rows)} rows -> {part_base}.csv")

    # Also write a schema-check CSV via csv module for exact header order.
    with (out / "NYC_EVENTS_MASTER_CUMULATIVE.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"exported {len(rows)} cumulative rows -> {base}.*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
