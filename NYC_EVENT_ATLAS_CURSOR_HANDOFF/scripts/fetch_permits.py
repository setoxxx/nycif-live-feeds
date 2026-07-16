#!/usr/bin/env python3
"""Fetch NYC permitted events for a date window; save hashed raw snapshot + staging candidates."""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from nyc_event_atlas.permit_mapping import map_permit, relevant
from nyc_event_atlas.sources.socrata import SocrataEventSource

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "nyc_permitted_events"


def ensure_source(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO sources(
          source_id, name, base_url, authority, confidence, method, refresh_interval
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SOURCE_ID,
            "NYC Permitted Event Information",
            "https://data.cityofnewyork.us",
            "official_government",
            "High",
            "socrata",
            "daily",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    verified_on = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    rows, meta = SocrataEventSource().fetch(start, end)
    candidates = [map_permit(r, verified_on=verified_on) for r in rows if relevant(r)]

    staging_path = ROOT / "data" / "staging" / "permit_candidates.json"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_text(
        json.dumps(
            {
                "meta": meta,
                "window": {"start": args.start, "end": args.end},
                "fetched_row_count": len(rows),
                "candidate_count": len(candidates),
                "records": candidates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Persist immutable snapshot metadata into SQLite (body already hashed by HTTP client).
    db = ROOT / "data" / "atlas.sqlite"
    with sqlite3.connect(db) as conn:
        ensure_source(conn)
        snapshot_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO raw_snapshots(
              snapshot_id, source_id, retrieved_at, request_url, request_params_json,
              http_status, content_type, etag, last_modified, sha256, local_path, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                SOURCE_ID,
                now,
                meta.get("url") or "",
                json.dumps({"start": args.start, "end": args.end}),
                meta.get("status"),
                meta.get("content_type"),
                meta.get("etag"),
                meta.get("last_modified"),
                meta.get("sha256") or "",
                meta.get("local_path") or "",
                "permit_mapping_v1",
            ),
        )
        conn.execute(
            "UPDATE sources SET last_checked_at=?, last_success_at=? WHERE source_id=?",
            (now, now, SOURCE_ID),
        )
        # Staging pointer for downstream ingest.
        (ROOT / "data" / "staging" / "permit_snapshot_id.txt").write_text(snapshot_id, encoding="utf-8")

    print(
        f"{len(rows)} relevant-type rows fetched; "
        f"{len(candidates)} candidates after relevance filter; "
        f"sha256={meta.get('sha256')}; "
        f"snapshot_id={snapshot_id}; "
        f"{staging_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
