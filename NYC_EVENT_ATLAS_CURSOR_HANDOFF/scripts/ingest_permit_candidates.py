#!/usr/bin/env python3
"""Normalize staged permit candidates, dedupe against canonical events, queue review.

Conservative default for the curated Atlas:
- Never invent coordinates, organizers, routes, or current dates from prior years.
- Exact permit / occurrence matches are skipped (already known).
- Fuzzy matches (score >= 88) go to review_queue as possible duplicates.
- Remaining high-confidence NEW permits go to review_queue as
  `new_occurrence_candidate` — they are NOT auto-inserted into `events`.
- Canonical EVENT_IDs / SERIES_IDs from the 827-row baseline are never overwritten.

Use --auto-accept-new only when an operator explicitly wants non-duplicate
Permitted rows inserted with newly allocated IDs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from nyc_event_atlas.dedupe import find_matches, occurrence_key
from nyc_event_atlas.id_allocator import allocate, next_numbers
from nyc_event_atlas.schema import EXPORT_COLUMNS, VALID_BOROUGHS

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging" / "permit_candidates.json"
SOURCE_ID = "nyc_permitted_events"


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


def ensure_59(rec: dict) -> dict:
    return {c: rec.get(c, "Unknown") for c in EXPORT_COLUMNS}


def queue_review(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    possible_event_id: str | None,
    issue_type: str,
    score: float | None,
    evidence: dict,
) -> str:
    review_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO review_queue(
          review_id, candidate_id, possible_event_id, issue_type,
          score, evidence_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            review_id,
            candidate_id,
            possible_event_id,
            issue_type,
            score,
            json.dumps(evidence, ensure_ascii=False),
        ),
    )
    conn.execute("UPDATE candidates SET state=? WHERE candidate_id=?", ("review", candidate_id))
    return review_id


def accept_new(
    conn: sqlite3.Connection,
    *,
    rec: dict,
    occ: str,
    snapshot_id: str | None,
    maxima: dict,
    year: int,
    now: str,
) -> str:
    permit_id = rec.get("PERMIT_ID") or "Unknown"
    event_id = allocate(rec["BOROUGH"], year, maxima)
    series_id = f"PERMIT-{permit_id}" if permit_id != "Unknown" else f"SERIES-{event_id}"
    rec["EVENT_ID"] = event_id
    rec["SERIES_ID"] = series_id
    rec["EVENT_STATUS"] = "Permitted"
    rec["PHOTO_VALUE"] = "Unknown"
    rec["NEWS_VALUE"] = "Unknown"
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
            rec.get("LAST_VERIFIED") or now[:10],
        ),
    )
    conn.execute(
        """
        INSERT INTO events(
          event_id, series_id, record_json, occurrence_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, series_id, json.dumps(rec, ensure_ascii=False), occ, now, now),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO event_sources(
          event_id, source_id, snapshot_id, source_url, supported_fields_json, confidence
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            SOURCE_ID,
            snapshot_id,
            rec.get("PRIMARY_SOURCE") or "",
            json.dumps(
                [
                    "EVENT_NAME",
                    "START_DATE",
                    "END_DATE",
                    "START_TIME",
                    "END_TIME",
                    "BOROUGH",
                    "VENUE",
                    "PERMIT_ID",
                    "PERMIT_AGENCY",
                ]
            ),
            "High",
        ),
    )
    return event_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto-accept-new",
        action="store_true",
        help="Insert high-confidence non-duplicate Permitted rows into events (off by default).",
    )
    args = parser.parse_args()

    if not STAGING.exists():
        raise SystemExit(f"Missing staging file: {STAGING}. Run fetch_permits.py first.")

    payload = json.loads(STAGING.read_text(encoding="utf-8"))
    candidates = payload.get("records") or []
    snapshot_id_path = ROOT / "data" / "staging" / "permit_snapshot_id.txt"
    snapshot_id = snapshot_id_path.read_text(encoding="utf-8").strip() if snapshot_id_path.exists() else None
    if not snapshot_id:
        raise SystemExit("Missing snapshot_id. Re-run fetch_permits.py so raw_snapshots is populated.")

    now = datetime.now(timezone.utc).isoformat()
    year = date.today().year
    report = {
        "generated_at_utc": now,
        "staging": str(STAGING),
        "snapshot_id": snapshot_id,
        "auto_accept_new": bool(args.auto_accept_new),
        "input_candidates": len(candidates),
        "skipped_exact_permit": 0,
        "skipped_exact_occurrence": 0,
        "queued_fuzzy_review": 0,
        "queued_new_occurrence_review": 0,
        "auto_accepted_new": 0,
        "rejected_invalid": 0,
        "review_ids": [],
        "accepted_event_ids": [],
        "safety": {
            "coordinates_invented": False,
            "baseline_ids_overwritten": False,
            "promotion_style_notes": "Atlas export is editorial CSV, separate from nycif public map.",
        },
    }

    seen_permit: set[str] = set()
    seen_occ: set[str] = set()

    with sqlite3.connect(ROOT / "data" / "atlas.sqlite") as conn:
        existing = load_canonical(conn)
        by_permit = {
            r.get("PERMIT_ID"): r
            for r in existing
            if r.get("PERMIT_ID") not in (None, "", "Unknown")
        }
        by_occ: dict[str, list[dict]] = {}
        for r in existing:
            by_occ.setdefault(occurrence_key(r), []).append(r)
        maxima = next_numbers(existing)

        for raw in candidates:
            rec = ensure_59(raw)
            # Hard rule: permit importer does not geocode or invent pins.
            rec["LATITUDE"] = "Unknown"
            rec["LONGITUDE"] = "Unknown"
            rec["ORGANIZER"] = rec.get("ORGANIZER") or "Unknown"
            if rec["ORGANIZER"] == "":
                rec["ORGANIZER"] = "Unknown"

            if rec.get("BOROUGH") not in VALID_BOROUGHS:
                report["rejected_invalid"] += 1
                continue
            if rec.get("START_DATE") in ("", "Unknown", "TBA"):
                report["rejected_invalid"] += 1
                continue

            permit_id = rec.get("PERMIT_ID") or "Unknown"
            occ = occurrence_key(rec)

            if permit_id != "Unknown" and (permit_id in by_permit or permit_id in seen_permit):
                report["skipped_exact_permit"] += 1
                continue
            if occ in by_occ or occ in seen_occ:
                report["skipped_exact_occurrence"] += 1
                continue

            candidate_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO candidates(
                  candidate_id, snapshot_id, source_record_id, source_url,
                  raw_json, normalized_json, extraction_confidence, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    snapshot_id,
                    permit_id,
                    rec.get("PRIMARY_SOURCE") or "",
                    json.dumps(raw, ensure_ascii=False),
                    json.dumps(rec, ensure_ascii=False),
                    1.0,
                    "new",
                ),
            )

            matches = find_matches(rec, existing, threshold=88)
            if matches:
                best_score, best_row = matches[0]
                review_id = queue_review(
                    conn,
                    candidate_id=candidate_id,
                    possible_event_id=best_row.get("EVENT_ID"),
                    issue_type="fuzzy_duplicate_candidate",
                    score=float(best_score),
                    evidence={
                        "candidate_name": rec.get("EVENT_NAME"),
                        "candidate_date": rec.get("START_DATE"),
                        "candidate_borough": rec.get("BOROUGH"),
                        "candidate_permit_id": permit_id,
                        "matched_event_id": best_row.get("EVENT_ID"),
                        "matched_name": best_row.get("EVENT_NAME"),
                        "score": best_score,
                        "top_matches": [
                            {
                                "event_id": m[1].get("EVENT_ID"),
                                "score": m[0],
                                "name": m[1].get("EVENT_NAME"),
                            }
                            for m in matches[:5]
                        ],
                    },
                )
                report["queued_fuzzy_review"] += 1
                report["review_ids"].append(review_id)
                if permit_id != "Unknown":
                    seen_permit.add(permit_id)
                seen_occ.add(occ)
                continue

            if args.auto_accept_new:
                event_id = accept_new(
                    conn,
                    rec=rec,
                    occ=occ,
                    snapshot_id=snapshot_id,
                    maxima=maxima,
                    year=year,
                    now=now,
                )
                conn.execute(
                    "UPDATE candidates SET state=? WHERE candidate_id=?",
                    ("accepted", candidate_id),
                )
                existing.append(rec)
                by_occ.setdefault(occ, []).append(rec)
                if permit_id != "Unknown":
                    by_permit[permit_id] = rec
                    seen_permit.add(permit_id)
                seen_occ.add(occ)
                report["auto_accepted_new"] += 1
                report["accepted_event_ids"].append(event_id)
            else:
                review_id = queue_review(
                    conn,
                    candidate_id=candidate_id,
                    possible_event_id=None,
                    issue_type="new_occurrence_candidate",
                    score=None,
                    evidence={
                        "candidate_name": rec.get("EVENT_NAME"),
                        "candidate_date": rec.get("START_DATE"),
                        "candidate_borough": rec.get("BOROUGH"),
                        "candidate_permit_id": permit_id,
                        "candidate_venue": rec.get("VENUE"),
                        "note": "High-confidence permit non-duplicate. Awaiting human verification before EVENT_ID allocation.",
                    },
                )
                report["queued_new_occurrence_review"] += 1
                report["review_ids"].append(review_id)
                if permit_id != "Unknown":
                    seen_permit.add(permit_id)
                seen_occ.add(occ)

    out = ROOT / "data" / "staging" / "permit_ingest_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"ingest complete: input={report['input_candidates']} "
        f"accepted={report['auto_accepted_new']} "
        f"fuzzy_review={report['queued_fuzzy_review']} "
        f"new_review={report['queued_new_occurrence_review']} "
        f"exact_permit_skip={report['skipped_exact_permit']} "
        f"exact_occ_skip={report['skipped_exact_occurrence']} "
        f"invalid={report['rejected_invalid']} "
        f"report={out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
