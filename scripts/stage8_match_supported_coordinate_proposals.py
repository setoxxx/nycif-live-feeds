#!/usr/bin/env python3
"""Match Stage 8 proposals to mutable supplemental staging occurrences.

Default mode is dry-run and never writes the staging feed. Apply mode is
intentionally unavailable until the match report proves one exact target per
proposal.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROPOSALS = ROOT / "data" / "reports" / "stage8_list_only_coordinate_proposals.json"
TARGET = ROOT / "data" / "supplemental_events_staging_feed.json"
REPORT = ROOT / "data" / "reports" / "stage8_supported_coordinate_match_report.json"


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def dataset(row: dict[str, Any]) -> str:
    src = source(row)
    return str(row.get("source_dataset") or row.get("dataset") or src.get("dataset") or src.get("name") or "").strip()


def source_id(row: dict[str, Any]) -> str:
    src = source(row)
    return str(
        row.get("source_event_id")
        or row.get("event_id")
        or row.get("eventid")
        or src.get("source_event_id")
        or src.get("event_id")
        or ""
    ).strip()


def day(row: dict[str, Any]) -> str:
    for key in ("date", "event_date", "start_date", "start_date_time", "start"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)[:10]
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(nycif.get("event_date") or "")[:10]


def location(row: dict[str, Any]) -> str:
    return str(row.get("location") or row.get("display_location") or row.get("event_location") or row.get("address") or "").strip()


def candidate_rows(payload: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            has_identity = bool(source_id(value))
            has_event_shape = any(value.get(key) not in (None, "") for key in ("title", "name", "event_name", "location", "display_location", "start_date_time", "date"))
            if has_identity and has_event_shape:
                output.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return output


def main() -> int:
    proposals_payload = load(PROPOSALS)
    proposals = proposals_payload.get("proposals") if isinstance(proposals_payload, dict) else []
    if not isinstance(proposals, list):
        raise RuntimeError("proposal artifact must contain proposals")
    target_rows = candidate_rows(load(TARGET))

    by_exact: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    by_source: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in target_rows:
        ds = norm(dataset(row))
        sid = norm(source_id(row))
        if not ds or not sid:
            continue
        by_source[(ds, sid)].append(row)
        if day(row):
            by_exact[(ds, sid, day(row))].append(row)

    results = []
    counts: Counter[str] = Counter()
    for proposal in proposals:
        ds = norm(proposal.get("source"))
        sid = norm(proposal.get("source_event_id"))
        date = str(proposal.get("date") or "")[:10]
        exact = by_exact.get((ds, sid, date), []) if date else []
        candidates = exact or by_source.get((ds, sid), [])
        # If source-only matching returns several recurring occurrences, keep only
        # those whose normalized location exactly matches the proposal.
        if len(candidates) != 1:
            loc = norm(proposal.get("location"))
            if loc:
                narrowed = [row for row in candidates if norm(location(row)) == loc]
                if narrowed:
                    candidates = narrowed
        status = "exact_one" if len(candidates) == 1 else ("unmatched" if not candidates else "ambiguous")
        counts[status] += 1
        results.append(
            {
                "canonical_id": proposal.get("canonical_id"),
                "source": proposal.get("source"),
                "source_event_id": proposal.get("source_event_id"),
                "date": proposal.get("date"),
                "location": proposal.get("location"),
                "status": status,
                "match_count": len(candidates),
                "matched_rows": [
                    {
                        "dataset": dataset(row),
                        "source_event_id": source_id(row),
                        "date": day(row),
                        "location": location(row),
                        "title": row.get("title") or row.get("name") or row.get("event_name"),
                    }
                    for row in candidates[:20]
                ],
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    exact_one = counts.get("exact_one", 0)
    report = {
        "artifact_type": "stage8_supported_coordinate_match_report",
        "schema_version": "1.0.0",
        "generated_at_utc": now,
        "target_path": str(TARGET.relative_to(ROOT)),
        "proposal_total": len(proposals),
        "target_candidate_rows": len(target_rows),
        "status_counts": dict(sorted(counts.items())),
        "all_proposals_match_exactly_once": exact_one == len(proposals),
        "production_data_modified": False,
        "apply_allowed": False,
        "qa_pass": exact_one == len(proposals),
        "results": results,
    }
    write(REPORT, report)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2, sort_keys=True))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
