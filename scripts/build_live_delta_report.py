#!/usr/bin/env python3
"""Build a live-update delta report for NYCIF staged events.

Compares the current staged feed against the previous staged snapshot so Howard can see
what newly appeared, what disappeared, and which new events may be worth PR outreach.

Outputs:
- data/live_delta_report.json
- data/previous_staged_live_events_snapshot.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CURRENT_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
PREVIOUS_SNAPSHOT_PATH = DATA_DIR / "previous_staged_live_events_snapshot.json"
DELTA_REPORT_PATH = DATA_DIR / "live_delta_report.json"

OUTREACH_KEYWORDS = re.compile(
    r"\b(press|media|premiere|opening|festival|parade|march|rally|ceremony|gala|concert|movie|film|theater|theatre|fashion|market|fair|expo|world cup|fifa|fan zone|celebrity|red carpet|performance|art|gallery|museum|launch|community|cultural)\b",
    re.IGNORECASE,
)
LOW_VALUE_KEYWORDS = re.compile(
    r"\b(little league|baseball|basketball|softball|tennis|volleyball|cricket|soccer|practice|clinic|after school|afterschool|children|kids|camp|permit|picnic)\b",
    re.IGNORECASE,
)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def event_key(row: dict[str, Any]) -> str:
    for key in ("id", "source_event_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "|".join(
        str(row.get(key) or "").strip().lower()
        for key in ("title", "borough", "display_location", "date", "start_date_time")
    )


def compact_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "source_event_id": row.get("source_event_id"),
        "title": row.get("title"),
        "category": row.get("category"),
        "borough": row.get("borough"),
        "display_location": row.get("display_location") or row.get("location"),
        "date": row.get("date"),
        "start_date_time": row.get("start_date_time"),
        "display_time": row.get("display_time"),
        "event_agency": row.get("event_agency"),
        "event_type": row.get("event_type"),
        "street_closure_type": row.get("street_closure_type"),
        "source_dataset": row.get("source_dataset"),
        "source_cemsid": row.get("source_cemsid") or [],
        "match_type": row.get("match_type"),
        "location_source": row.get("location_source"),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
    }


def comparable_signature(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "title",
            "category",
            "borough",
            "display_location",
            "location",
            "date",
            "start_date_time",
            "end_date_time",
            "event_type",
            "street_closure_type",
            "lat",
            "lng",
        )
    }


def outreach_score(row: dict[str, Any]) -> tuple[int, list[str]]:
    text = " ".join(
        str(row.get(key) or "")
        for key in (
            "title",
            "category",
            "event_type",
            "street_closure_type",
            "event_agency",
            "display_location",
            "borough",
        )
    )
    score = 0
    reasons: list[str] = []
    if OUTREACH_KEYWORDS.search(text):
        score += 50
        reasons.append("public-facing/media-friendly wording")
    if str(row.get("category") or "").lower() in {"arts", "market", "parade"}:
        score += 30
        reasons.append("strong event category for coverage")
    if str(row.get("borough") or "").lower() == "manhattan":
        score += 10
        reasons.append("Manhattan event")
    if row.get("source_event_id"):
        score += 5
        reasons.append("traceable live event id")
    if LOW_VALUE_KEYWORDS.search(text):
        score -= 35
        reasons.append("likely routine recreation/permit event")
    return score, reasons


def outreach_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    score, reasons = outreach_score(row)
    if score < 35:
        return None
    event = compact_event(row)
    event["outreach_score"] = score
    event["outreach_reasons"] = reasons
    event["suggested_next_step"] = "Look for organizer/PR contact, event website, agency page, venue press contact, or social announcement."
    event["contact_status"] = "needs_research"
    return event


def main() -> int:
    current_payload = load_json_file(CURRENT_FEED_PATH, {})
    previous_payload = load_json_file(PREVIOUS_SNAPSHOT_PATH, {})
    current_rows = rows_from_payload(current_payload)
    previous_rows = rows_from_payload(previous_payload)

    current_by_key = {event_key(row): row for row in current_rows if event_key(row)}
    previous_by_key = {event_key(row): row for row in previous_rows if event_key(row)}

    added_keys = sorted(set(current_by_key) - set(previous_by_key))
    removed_keys = sorted(set(previous_by_key) - set(current_by_key))
    shared_keys = sorted(set(current_by_key) & set(previous_by_key))
    changed_keys = [
        key for key in shared_keys
        if comparable_signature(current_by_key[key]) != comparable_signature(previous_by_key[key])
    ]

    added_events = [compact_event(current_by_key[key]) for key in added_keys]
    removed_events = [compact_event(previous_by_key[key]) for key in removed_keys]
    changed_events = [
        {
            "before": compact_event(previous_by_key[key]),
            "after": compact_event(current_by_key[key]),
        }
        for key in changed_keys
    ]
    candidates = [candidate for key in added_keys if (candidate := outreach_candidate(current_by_key[key]))]
    candidates.sort(key=lambda row: (-(row.get("outreach_score") or 0), row.get("date") or "", row.get("title") or ""))

    generated_at = datetime.now(timezone.utc).isoformat()
    previous_generated_at = None
    if isinstance(previous_payload, dict):
        previous_generated_at = previous_payload.get("generated_at_utc")
    current_generated_at = None
    if isinstance(current_payload, dict):
        current_generated_at = current_payload.get("generated_at_utc")

    report = {
        "generated_at_utc": generated_at,
        "current_feed_generated_at_utc": current_generated_at,
        "previous_snapshot_generated_at_utc": previous_generated_at,
        "baseline_available": bool(previous_rows),
        "current_staged_count": len(current_rows),
        "previous_staged_count": len(previous_rows),
        "added_count": len(added_events),
        "removed_count": len(removed_events),
        "changed_count": len(changed_events),
        "net_change": len(current_rows) - len(previous_rows),
        "pr_outreach_candidate_count": len(candidates),
        "summary": {
            "added": len(added_events),
            "removed": len(removed_events),
            "changed": len(changed_events),
            "net_change": len(current_rows) - len(previous_rows),
            "pr_outreach_candidates": len(candidates),
        },
        "added_events": added_events,
        "removed_events": removed_events[:200],
        "changed_events": changed_events[:200],
        "pr_outreach_candidates": candidates[:100],
        "notes": [
            "First run after installing this report will use an empty or stale baseline if no previous snapshot exists.",
            "PR outreach candidates are heuristic leads, not confirmed PR contacts.",
            "Routine parks/youth sports events are down-ranked unless other media-friendly signals appear.",
        ],
    }

    save_json_file(DELTA_REPORT_PATH, report)
    snapshot = {
        "generated_at_utc": current_generated_at or generated_at,
        "snapshot_saved_at_utc": generated_at,
        "source": str(CURRENT_FEED_PATH.relative_to(ROOT)),
        "events": current_rows,
    }
    save_json_file(PREVIOUS_SNAPSHOT_PATH, snapshot)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
