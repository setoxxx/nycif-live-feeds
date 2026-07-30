#!/usr/bin/env python3
"""Rebuild the possible-duplicate queue without a 500-group cap.

The approved output can contain folded review-supplemental projections. The
projector's accepted canonical population is therefore reconstructed from:
- approved records whose data layer is ``approved_staged``; plus
- every record in the review projection.
The resulting canonical-ID union must equal strict reconciliation exactly.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
APPROVED = DATA / "events_discovery_v02_approved.json"
REVIEW = DATA / "events_discovery_v02_review.json"
RECONCILIATION = DATA / "events_discovery_reconciliation_v02.json"
OUTPUT = DATA / "events_discovery_possible_duplicates_v02.json"


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def write(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def data_layer(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(nycif.get("data_layer") or "").strip()


def canonical_union(*collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for collection in collections:
        for row in collection:
            cid = str(row.get("id") or "").strip()
            if not cid:
                raise RuntimeError("duplicate audit encountered a row without canonical id")
            existing = by_id.get(cid)
            if existing is None:
                by_id[cid] = row
                continue
            for key in ("title", "start_date_time", "borough"):
                left = str(existing.get(key) or "")
                right = str(row.get(key) or "")
                if left and right and left != right:
                    raise RuntimeError(f"canonical projection mismatch for {cid}: {key}")
    return list(by_id.values())


def canonical_population(
    approved: list[dict[str, Any]], review: list[dict[str, Any]], expected: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    approved_staged = [row for row in approved if data_layer(row) == "approved_staged"]
    canonical = canonical_union(approved_staged, review)
    diagnostics = {
        "approved_projection_count": len(approved),
        "approved_staged_projection_count": len(approved_staged),
        "approved_folded_supplemental_projection_count": len(approved) - len(approved_staged),
        "review_projection_count": len(review),
        "canonical_union_count": len(canonical),
    }
    if len(canonical) != expected:
        raise RuntimeError(
            "canonical projector split mismatch: "
            f"expected {expected}, got {len(canonical)}; diagnostics={diagnostics}"
        )
    return canonical, diagnostics


def possible_duplicates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        title = re.sub(r"[^a-z0-9]+", " ", str(event.get("title") or "").lower()).strip()
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        day = str(nycif.get("event_date") or str(event.get("start_date_time") or "")[:10])
        borough = str(event.get("borough") or "").lower()
        if title in {"celebration", "party", "event", "picnic", "memorial", "special event"}:
            continue
        if not title or not day:
            continue
        buckets[(title, day, borough)].append(event)

    groups: list[dict[str, Any]] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        datasets = {
            str((member.get("source") or {}).get("dataset") or "")
            for member in members
            if isinstance(member.get("source"), dict)
        }
        ids = sorted(str(member.get("id") or "") for member in members)
        if len(datasets) < 2 and len(set(ids)) < 2:
            continue
        groups.append(
            {
                "group_key": f"{key[0]}|{key[1]}|{key[2]}",
                "count": len(members),
                "ids": ids,
                "titles": sorted({str(member.get("title") or "") for member in members}),
                "source_datasets": sorted(dataset for dataset in datasets if dataset),
                "reason_for_review": "same_title_date_borough_insufficient_for_auto_merge",
                "recommended_action": "manual_duplicate_review",
                "auto_merge_allowed": False,
            }
        )
    groups.sort(key=lambda item: (-int(item["count"]), str(item["group_key"])))
    return groups


def main() -> int:
    approved = rows(load(APPROVED))
    review = rows(load(REVIEW))
    reconciliation = load(RECONCILIATION)
    expected = int(reconciliation.get("accepted_canonical_records") or 0)
    canonical, diagnostics = canonical_population(approved, review, expected)

    groups = possible_duplicates(canonical)
    candidate_ids = {cid for group in groups for cid in group["ids"]}
    candidate_record_count = sum(int(group["count"]) for group in groups)
    payload = {
        "artifact_type": "events_discovery_possible_duplicates_v02",
        "schema_version": "2.1.0",
        "generated_at_utc": reconciliation.get("generated_at_utc"),
        "canonical_population_count": len(canonical),
        **diagnostics,
        "count": len(groups),
        "candidate_record_count": candidate_record_count,
        "unique_candidate_id_count": len(candidate_ids),
        "truncated": False,
        "auto_merge_allowed": False,
        "groups": groups,
    }
    write(OUTPUT, payload)
    print(json.dumps({key: value for key, value in payload.items() if key != "groups"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
