"""Shared candidate → review_queue ingest (no silent canonical growth)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dedupe import find_matches, occurrence_key
from .schema import EXPORT_COLUMNS, VALID_BOROUGHS

ROOT = Path(__file__).resolve().parents[2]


def ensure_59(rec: dict) -> dict:
    return {c: rec.get(c, "Unknown") for c in EXPORT_COLUMNS}


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


def ensure_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    name: str,
    base_url: str,
    authority: str,
    confidence: str,
    method: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO sources(
          source_id, name, base_url, authority, confidence, method
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_id, name, base_url, authority, confidence, method),
    )


def save_snapshot(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    meta: dict,
    params: dict | None = None,
    parser_version: str,
) -> str:
    snapshot_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO raw_snapshots(
          snapshot_id, source_id, retrieved_at, request_url, request_params_json,
          http_status, content_type, etag, last_modified, sha256, local_path, parser_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            source_id,
            now,
            meta.get("url") or "",
            json.dumps(params or {}),
            meta.get("status"),
            meta.get("content_type"),
            meta.get("etag"),
            meta.get("last_modified"),
            meta.get("sha256") or "",
            meta.get("local_path") or "",
            parser_version,
        ),
    )
    conn.execute(
        "UPDATE sources SET last_checked_at=?, last_success_at=? WHERE source_id=?",
        (now, now, source_id),
    )
    return snapshot_id


def queue_normalized_candidates(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    snapshot_id: str,
    records: list[dict[str, Any]],
    fuzzy_threshold: float = 88.0,
) -> dict:
    """Insert candidates and open review rows. Never allocates EVENT_IDs."""
    existing = load_canonical(conn)
    by_permit = {
        r.get("PERMIT_ID"): r
        for r in existing
        if r.get("PERMIT_ID") not in (None, "", "Unknown")
    }
    by_occ: dict[str, list[dict]] = {}
    for r in existing:
        by_occ.setdefault(occurrence_key(r), []).append(r)

    # Also treat open review candidates as already-seen so re-runs do not
    # flood the queue with duplicate rows.
    open_permits: set[str] = set()
    open_occs: set[str] = set()
    for (normalized_json,) in conn.execute(
        """
        SELECT c.normalized_json
        FROM review_queue r
        JOIN candidates c ON c.candidate_id = r.candidate_id
        WHERE r.status = 'open'
        """
    ):
        try:
            rec = json.loads(normalized_json)
        except json.JSONDecodeError:
            continue
        pid = rec.get("PERMIT_ID") or "Unknown"
        if pid != "Unknown":
            open_permits.add(pid)
        open_occs.add(occurrence_key(rec))

    seen_permit: set[str] = set()
    seen_occ: set[str] = set()
    report = {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "input": len(records),
        "skipped_exact_permit": 0,
        "skipped_exact_occurrence": 0,
        "skipped_open_review": 0,
        "queued_fuzzy_review": 0,
        "queued_new_occurrence_review": 0,
        "rejected_invalid": 0,
    }

    for raw in records:
        rec = ensure_59(raw)
        # Never invent coordinates in adapters.
        if rec.get("LATITUDE") in ("", None):
            rec["LATITUDE"] = "Unknown"
        if rec.get("LONGITUDE") in ("", None):
            rec["LONGITUDE"] = "Unknown"
        if (rec["LATITUDE"] == "Unknown") != (rec["LONGITUDE"] == "Unknown"):
            rec["LATITUDE"] = "Unknown"
            rec["LONGITUDE"] = "Unknown"

        if rec.get("BOROUGH") not in VALID_BOROUGHS:
            report["rejected_invalid"] += 1
            continue
        if rec.get("START_DATE") in ("", "Unknown"):
            # TBA is allowed for official planned events.
            if rec.get("START_DATE") != "TBA" and rec.get("EVENT_STATUS") != "TBA":
                report["rejected_invalid"] += 1
                continue

        permit_id = rec.get("PERMIT_ID") or "Unknown"
        occ = occurrence_key(rec)
        if permit_id != "Unknown" and (
            permit_id in by_permit or permit_id in seen_permit or permit_id in open_permits
        ):
            if permit_id in open_permits:
                report["skipped_open_review"] += 1
            else:
                report["skipped_exact_permit"] += 1
            continue
        if occ in by_occ or occ in seen_occ or occ in open_occs:
            if occ in open_occs:
                report["skipped_open_review"] += 1
            else:
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
                permit_id if permit_id != "Unknown" else rec.get("EVENT_NAME"),
                rec.get("PRIMARY_SOURCE") or "",
                json.dumps(raw, ensure_ascii=False),
                json.dumps(rec, ensure_ascii=False),
                1.0,
                "new",
            ),
        )

        matches = find_matches(rec, existing, threshold=fuzzy_threshold)
        review_id = str(uuid.uuid4())
        if matches:
            best_score, best_row = matches[0]
            issue = "fuzzy_duplicate_candidate"
            evidence = {
                "candidate_name": rec.get("EVENT_NAME"),
                "candidate_date": rec.get("START_DATE"),
                "candidate_borough": rec.get("BOROUGH"),
                "matched_event_id": best_row.get("EVENT_ID"),
                "matched_name": best_row.get("EVENT_NAME"),
                "score": best_score,
            }
            possible = best_row.get("EVENT_ID")
            report["queued_fuzzy_review"] += 1
            score = float(best_score)
        else:
            issue = "new_occurrence_candidate"
            evidence = {
                "candidate_name": rec.get("EVENT_NAME"),
                "candidate_date": rec.get("START_DATE"),
                "candidate_borough": rec.get("BOROUGH"),
                "candidate_venue": rec.get("VENUE"),
                "source_id": source_id,
                "note": "Awaiting human accept before EVENT_ID allocation.",
            }
            possible = None
            report["queued_new_occurrence_review"] += 1
            score = None

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
                possible,
                issue,
                score,
                json.dumps(evidence, ensure_ascii=False),
            ),
        )
        conn.execute(
            "UPDATE candidates SET state=? WHERE candidate_id=?", ("review", candidate_id)
        )
        if permit_id != "Unknown":
            seen_permit.add(permit_id)
        seen_occ.add(occ)

    return report
