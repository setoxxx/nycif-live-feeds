#!/usr/bin/env python3
"""Build reader-safe News Desk signals from the canonical certified projection.

Operator ranking inputs never control location. A News Desk row is emitted only
when its V2 occurrence exists in the canonical discovery projection and that
canonical occurrence is MAP_READY with certified_pin=true. Coordinates and
public location are copied from the canonical projection, never from operator
lane input.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows, utc_now, write_json
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows, utc_now, write_json
    from occurrence_identity_contract import occurrence_key_v2

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
MONEY = ROOT / "data" / "photographer_assignment_calendar_2mo.json"
VIRAL = ROOT / "data" / "photographer_viral_recurrence_matches.json"
OUT_MONEY = "data/reader-safe/news-desk-money-v02.json"
OUT_VIRAL = "data/reader-safe/news-desk-viral-v02.json"
OUT_STATUS = "data/reader-safe/news-desk-status-v02.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
        if nycif.get("map_eligibility_state") != "MAP_READY" or nycif.get("certified_pin") is not True:
            continue
        if row.get("latitude") is None or row.get("longitude") is None:
            continue
        out[occurrence_key_v2(row)] = row
    return out


def safe_row(operator_row: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    src = canonical.get("source") if isinstance(canonical.get("source"), dict) else {}
    return {
        "id": canonical.get("id"),
        "title": canonical.get("title"),
        "date": str(canonical.get("start_date_time") or (canonical.get("nycif") or {}).get("event_date") or "")[:10],
        "start_date_time": canonical.get("start_date_time"),
        "end_date_time": canonical.get("end_date_time"),
        "borough": canonical.get("borough"),
        "display_location": canonical.get("location"),
        "latitude": canonical.get("latitude"),
        "longitude": canonical.get("longitude"),
        "category": canonical.get("category"),
        "source": {
            "dataset": src.get("dataset"),
            "source_event_id": src.get("source_event_id"),
        },
        "coordinate_status": "map_ready",
        "map_eligibility_state": "MAP_READY",
        "certified_pin": True,
        "photo_pick": bool(operator_row.get("photo_pick")),
        "assignment_score": operator_row.get("assignment_score"),
    }


def build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    generated_at = utc_now()
    canonical_rows = extract_rows(load(CANONICAL))
    index = canonical_index(canonical_rows)

    money_payload = load(MONEY)
    money_rows = money_payload.get("events", []) if isinstance(money_payload, dict) else []
    safe_money: list[dict[str, Any]] = []
    money_dropped = 0
    for row in money_rows:
        if not isinstance(row, dict):
            continue
        canonical = index.get(occurrence_key_v2(row))
        if canonical is None:
            money_dropped += 1
            continue
        safe_money.append(safe_row(row, canonical))

    viral_payload = load(VIRAL)
    matches = viral_payload.get("matches", []) if isinstance(viral_payload, dict) else []
    safe_matches: list[dict[str, Any]] = []
    viral_dropped = 0
    for match in matches:
        if not isinstance(match, dict) or match.get("recurrence_label") != "returning_likely":
            continue
        current = match.get("current") if isinstance(match.get("current"), dict) else None
        if current is None:
            continue
        canonical = index.get(occurrence_key_v2(current))
        if canonical is None:
            viral_dropped += 1
            continue
        safe_matches.append({
            "current": safe_row(current, canonical),
            "recurrence_label": "returning_likely",
        })

    money_out = {
        "schema_version": "nycif-news-desk-money-v02",
        "generated_at_utc": generated_at,
        "authority": "canonical_discovery_v02",
        "events": safe_money,
    }
    viral_out = {
        "schema_version": "nycif-news-desk-viral-v02",
        "generated_at_utc": generated_at,
        "authority": "canonical_discovery_v02",
        "matches": safe_matches,
    }
    status = {
        "schema_version": "nycif-news-desk-status-v02",
        "generated_at_utc": generated_at,
        "canonical_map_ready_occurrences": len(index),
        "money_input_rows": len([r for r in money_rows if isinstance(r, dict)]),
        "money_emitted_rows": len(safe_money),
        "money_rows_without_canonical_exact_authority": money_dropped,
        "viral_returning_input_rows": sum(1 for m in matches if isinstance(m, dict) and m.get("recurrence_label") == "returning_likely"),
        "viral_emitted_rows": len(safe_matches),
        "viral_rows_without_canonical_exact_authority": viral_dropped,
        "unsupported_exact_pin_count": 0,
        "browser_raw_repository_required": False,
    }
    return money_out, viral_out, status


def main() -> int:
    money, viral, status = build()
    write_json(OUT_MONEY, money)
    write_json(OUT_VIRAL, viral)
    write_json(OUT_STATUS, status)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
