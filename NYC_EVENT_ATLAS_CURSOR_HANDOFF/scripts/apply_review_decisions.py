#!/usr/bin/env python3
"""Apply human review decisions: accept → allocate EVENT_ID; reject → close.

Decision CSV columns (header required):
  review_id,decision,resolution_notes

decision values:
  accept  — allocate new EVENT_ID from normalized candidate; close review
  reject  — close review without inserting
  defer   — leave open (no-op)

Never overwrites existing EVENT_IDs. Never invents coordinates.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from nyc_event_atlas.dedupe import occurrence_key
from nyc_event_atlas.id_allocator import allocate, next_numbers
from nyc_event_atlas.schema import EXPORT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def load_canonical(conn: sqlite3.Connection) -> list[dict]:
    rows = []
    for event_id, series_id, record_json in conn.execute(
        "SELECT event_id, series_id, record_json FROM events"
    ):
        rec = json.loads(record_json)
        rec["EVENT_ID"] = event_id
        rec["SERIES_ID"] = series_id
        rows.append(rec)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decisions",
        required=True,
        help="CSV with review_id,decision,resolution_notes",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="After applies, rebuild cumulative + Part export and validate",
    )
    args = parser.parse_args()

    decisions_path = Path(args.decisions)
    if not decisions_path.is_absolute():
        decisions_path = ROOT / decisions_path
    if not decisions_path.exists():
        raise SystemExit(f"Missing decisions file: {decisions_path}")

    with decisions_path.open(encoding="utf-8-sig", newline="") as f:
        decisions = list(csv.DictReader(f))
    if not decisions:
        raise SystemExit("Decisions CSV is empty")

    now = datetime.now(timezone.utc).isoformat()
    year = date.today().year
    report = {
        "generated_at_utc": now,
        "decisions_file": str(decisions_path),
        "accepted": 0,
        "rejected": 0,
        "deferred": 0,
        "errors": [],
        "accepted_event_ids": [],
    }

    with sqlite3.connect(ROOT / "data" / "atlas.sqlite") as conn:
        existing = load_canonical(conn)
        maxima = next_numbers(existing)

        for row in decisions:
            review_id = (row.get("review_id") or "").strip()
            decision = (row.get("decision") or "").strip().lower()
            notes = (row.get("resolution_notes") or "").strip() or decision
            if not review_id:
                report["errors"].append("missing review_id")
                continue
            if decision == "defer":
                report["deferred"] += 1
                continue

            cur = conn.execute(
                """
                SELECT r.status, r.candidate_id, c.normalized_json, c.source_url, c.snapshot_id
                FROM review_queue r
                JOIN candidates c ON c.candidate_id = r.candidate_id
                WHERE r.review_id = ?
                """,
                (review_id,),
            ).fetchone()
            if not cur:
                report["errors"].append(f"{review_id}: not found")
                continue
            status, candidate_id, normalized_json, source_url, snapshot_id = cur
            if status != "open":
                report["errors"].append(f"{review_id}: already {status}")
                continue

            if decision == "reject":
                conn.execute(
                    "UPDATE review_queue SET status=?, resolution=? WHERE review_id=?",
                    ("rejected", notes, review_id),
                )
                conn.execute(
                    "UPDATE candidates SET state=? WHERE candidate_id=?",
                    ("rejected", candidate_id),
                )
                report["rejected"] += 1
                continue

            if decision != "accept":
                report["errors"].append(f"{review_id}: unknown decision {decision!r}")
                continue

            rec = {c: "Unknown" for c in EXPORT_COLUMNS}
            rec.update(json.loads(normalized_json))
            # Hard safety: do not accept invented/partial coords.
            if (rec.get("LATITUDE") in ("", "Unknown")) != (
                rec.get("LONGITUDE") in ("", "Unknown")
            ):
                rec["LATITUDE"] = "Unknown"
                rec["LONGITUDE"] = "Unknown"

            borough = rec.get("BOROUGH")
            event_id = allocate(borough, year, maxima)
            series_id = rec.get("SERIES_ID")
            if not series_id or series_id == "Unknown":
                permit = rec.get("PERMIT_ID")
                series_id = (
                    f"PERMIT-{permit}"
                    if permit not in (None, "", "Unknown")
                    else f"SERIES-{event_id}"
                )
            rec["EVENT_ID"] = event_id
            rec["SERIES_ID"] = series_id
            if rec.get("EVENT_STATUS") in ("", "Unknown"):
                rec["EVENT_STATUS"] = "Confirmed"
            if rec.get("LAST_VERIFIED") in ("", "Unknown"):
                rec["LAST_VERIFIED"] = date.today().isoformat()
            # Editorial scores stay Unknown unless reviewer supplied them.
            for score_field in ("PHOTO_VALUE", "NEWS_VALUE"):
                if rec.get(score_field) in ("", None):
                    rec[score_field] = "Unknown"

            occ = occurrence_key(rec)
            conn.execute(
                """
                INSERT OR IGNORE INTO event_series(
                  series_id, canonical_name, organizer, first_seen_at, last_verified_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    series_id,
                    rec["EVENT_NAME"],
                    rec.get("ORGANIZER") or "Unknown",
                    now,
                    rec.get("LAST_VERIFIED"),
                ),
            )
            conn.execute(
                """
                INSERT INTO events(
                  event_id, series_id, record_json, occurrence_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    series_id,
                    json.dumps(rec, ensure_ascii=False),
                    occ,
                    now,
                    now,
                ),
            )
            # Best-effort source link (source_id may be unknown for older candidates).
            source_id = conn.execute(
                "SELECT source_id FROM raw_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            if source_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO event_sources(
                      event_id, source_id, snapshot_id, source_url,
                      supported_fields_json, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        source_id[0],
                        snapshot_id,
                        source_url or rec.get("PRIMARY_SOURCE") or "",
                        json.dumps(["EVENT_NAME", "START_DATE", "BOROUGH", "VENUE"]),
                        rec.get("SOURCE_CONFIDENCE") or "High",
                    ),
                )
            conn.execute(
                "UPDATE review_queue SET status=?, resolution=? WHERE review_id=?",
                ("accepted", f"{notes}; allocated {event_id}", review_id),
            )
            conn.execute(
                "UPDATE candidates SET state=? WHERE candidate_id=?",
                ("accepted", candidate_id),
            )
            report["accepted"] += 1
            report["accepted_event_ids"].append(event_id)
            existing.append(rec)

    out = ROOT / "data" / "staging" / "review_apply_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Write accepted ids for Part export pickup.
    ingest_path = ROOT / "data" / "staging" / "permit_ingest_report.json"
    # Keep a dedicated apply report; export_from_db reads accepted_event_ids from this if present.
    apply_ids_path = ROOT / "data" / "staging" / "accepted_event_ids.json"
    apply_ids_path.write_text(
        json.dumps(
            {
                "accepted_event_ids": report["accepted_event_ids"],
                "generated_at_utc": now,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"applied decisions: accepted={report['accepted']} rejected={report['rejected']} "
        f"deferred={report['deferred']} errors={len(report['errors'])} report={out}"
    )

    if args.export:
        import subprocess
        import sys

        subprocess.check_call(
            [sys.executable, "scripts/export_from_db.py", "--out", "data/exports"],
            cwd=ROOT,
        )
        subprocess.check_call(
            [
                sys.executable,
                "scripts/validate_exports.py",
                str(ROOT / "data/exports/NYC_EVENTS_MASTER_CUMULATIVE.csv"),
            ],
            cwd=ROOT,
        )
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
