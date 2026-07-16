#!/usr/bin/env python3
"""Export open review_queue rows to CSV for human accept/reject."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = ROOT / "data" / "staging" / "open_review_queue.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ROOT / "data" / "atlas.sqlite") as conn:
        rows = conn.execute(
            """
            SELECT r.review_id, r.issue_type, r.score, r.status, r.possible_event_id,
                   c.source_record_id, c.source_url, c.normalized_json,
                   s.source_id
            FROM review_queue r
            JOIN candidates c ON c.candidate_id = r.candidate_id
            LEFT JOIN raw_snapshots s ON s.snapshot_id = c.snapshot_id
            WHERE r.status = 'open'
            ORDER BY json_extract(c.normalized_json, '$.START_DATE'),
                     json_extract(c.normalized_json, '$.EVENT_NAME')
            """
        ).fetchall()

    fields = [
        "review_id",
        "issue_type",
        "source_id",
        "START_DATE",
        "BOROUGH",
        "EVENT_NAME",
        "VENUE",
        "CATEGORY",
        "ORGANIZER",
        "PRIMARY_SOURCE",
        "possible_event_id",
        "score",
        "decision",
        "resolution_notes",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for (
            review_id,
            issue_type,
            score,
            _status,
            possible_event_id,
            _source_record_id,
            source_url,
            normalized_json,
            source_id,
        ) in rows:
            rec = json.loads(normalized_json)
            w.writerow(
                {
                    "review_id": review_id,
                    "issue_type": issue_type,
                    "source_id": source_id or "",
                    "START_DATE": rec.get("START_DATE"),
                    "BOROUGH": rec.get("BOROUGH"),
                    "EVENT_NAME": rec.get("EVENT_NAME"),
                    "VENUE": rec.get("VENUE"),
                    "CATEGORY": rec.get("CATEGORY"),
                    "ORGANIZER": rec.get("ORGANIZER"),
                    "PRIMARY_SOURCE": rec.get("PRIMARY_SOURCE") or source_url,
                    "possible_event_id": possible_event_id or "",
                    "score": score if score is not None else "",
                    "decision": "",
                    "resolution_notes": "",
                }
            )
    print(f"wrote {len(rows)} open review rows -> {out}")
    print("Fill decision=accept|reject|defer then run:")
    print("  python scripts/apply_review_decisions.py --decisions data/staging/open_review_queue.csv --export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
