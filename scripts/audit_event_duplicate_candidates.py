#!/usr/bin/env python3
"""Audit canonical discovery events for exact and near-duplicate occurrence candidates.

This is an audit-only companion to the canonical projector. It never mutates,
merges, promotes, geocodes, or publishes an event. OccurrenceIdentityV2 remains
the occurrence authority; this script only identifies records requiring review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
DEFAULT_OUTPUT = ROOT / "data" / "events_discovery_duplicate_audit_v03.json"

_STOP_WORDS = {"the", "a", "an", "at", "of", "and", "for", "in", "on", "nyc", "new", "york"}


def _rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "events", "records", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return " ".join(token for token in text.split() if token not in _STOP_WORDS)


def _date(row: dict) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    value = nycif.get("event_date") or row.get("start_date_time") or row.get("start") or ""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    return match.group(1) if match else ""


def _time(row: dict) -> str:
    value = row.get("start_date_time") or row.get("start") or ""
    match = re.search(r"T(\d{2}:\d{2})", str(value))
    return match.group(1) if match else ""


def _source(row: dict) -> tuple[str, str]:
    src = row.get("source") if isinstance(row.get("source"), dict) else {}
    return str(src.get("dataset") or ""), str(src.get("source_event_id") or "")


def _candidate(row: dict) -> dict:
    dataset, source_event_id = _source(row)
    return {
        "canonical_id": row.get("id"),
        "title": row.get("title"),
        "date": _date(row),
        "start_time": _time(row),
        "borough": row.get("borough"),
        "location": row.get("location"),
        "source_dataset": dataset,
        "source_event_id": source_event_id,
        "event_role": row.get("event_role"),
        "parent_event_id": row.get("parent_event_id"),
    }


def audit(rows: list[dict]) -> dict:
    by_exact: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    by_near: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    for row in rows:
        title = _norm(row.get("title"))
        day = _date(row)
        borough = _norm(row.get("borough"))
        location = _norm(row.get("location"))
        start_time = _time(row)
        if not title or not day:
            continue
        by_exact[(title, day, start_time, location)].append(row)
        by_near[(title, day, borough)].append(row)

    exact_groups = []
    for key, members in by_exact.items():
        ids = {str(row.get("id") or "") for row in members}
        if len(members) < 2 or len(ids) < 2:
            continue
        exact_groups.append({
            "group_key": "|".join(key),
            "reason": "same_normalized_title_date_time_location",
            "auto_merge_allowed": False,
            "records": [_candidate(row) for row in members],
        })

    near_groups = []
    exact_id_sets = [{str(r.get("canonical_id") or "") for r in g["records"]} for g in exact_groups]
    for key, members in by_near.items():
        ids = {str(row.get("id") or "") for row in members}
        datasets = {_source(row)[0] for row in members}
        if len(members) < 2 or len(ids) < 2:
            continue
        if any(ids == exact_ids for exact_ids in exact_id_sets):
            continue
        if len(datasets) < 2 and len({(_time(row), _norm(row.get("location"))) for row in members}) > 1:
            continue
        near_groups.append({
            "group_key": "|".join(key),
            "reason": "same_normalized_title_date_borough_requires_identity_review",
            "auto_merge_allowed": False,
            "records": [_candidate(row) for row in members],
        })

    exact_groups.sort(key=lambda g: (-len(g["records"]), g["group_key"]))
    near_groups.sort(key=lambda g: (-len(g["records"]), g["group_key"]))
    candidate_ids = {
        str(record.get("canonical_id") or "")
        for group in exact_groups + near_groups
        for record in group["records"]
        if record.get("canonical_id")
    }

    return {
        "artifact_type": "events_discovery_duplicate_audit_v03",
        "schema_version": "3.0.0",
        "audit_only": True,
        "auto_merge_allowed": False,
        "canonical_population_count": len(rows),
        "exact_candidate_group_count": len(exact_groups),
        "near_candidate_group_count": len(near_groups),
        "unique_candidate_id_count": len(candidate_ids),
        "exact_groups": exact_groups,
        "near_groups": near_groups,
        "release_gate": "PASS" if not exact_groups and not near_groups else "REVIEW_REQUIRED",
        "authority_note": "OccurrenceIdentityV2 remains occurrence authority; this audit cannot merge canonical occurrences.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = audit(_rows(payload))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "canonical_population_count",
        "exact_candidate_group_count",
        "near_candidate_group_count",
        "unique_candidate_id_count",
        "release_gate",
    )}, sort_keys=True))
    return 0 if report["release_gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
