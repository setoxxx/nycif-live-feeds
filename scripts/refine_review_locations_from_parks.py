#!/usr/bin/env python3
"""Resolve unresolved review locations from exact NYC Parks counterparts.

A review proposal is resolved only when the committed NYC Parks snapshot has:

- the exact normalized title;
- the exact event date;
- distinctive location-token agreement;
- valid coordinates inside exactly one official NYC DCP borough polygon; and
- one borough with a tight coordinate cluster when multiple counterparts exist.

This is an audit-only proposal stage. It does not edit a feed, cache, WordPress,
or any public map surface.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.audit_review_location_coverage import ROOT
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.refine_review_location_cross_source import (
        safe_cluster,
        semantic_location_tokens,
        title_key,
    )
    from scripts.resolve_remaining_review_locations import borough_for_point, load_boundaries
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from audit_review_location_coverage import ROOT
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from refine_review_location_cross_source import safe_cluster, semantic_location_tokens, title_key
    from resolve_remaining_review_locations import borough_for_point, load_boundaries
    from schema_v1_common import utc_now

PARKS_SNAPSHOT = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "review_location_parks_counterpart_audit.json"
DEFAULT_PROPOSALS = ROOT / "data" / "staging" / "review_location_parks_counterpart_proposals.json"


def load_parks_events(path: Path = PARKS_SNAPSHOT) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError(f"NYC Parks snapshot has no events array: {path}")
    return [row for row in rows if isinstance(row, dict)]


def parks_event_date(row: dict[str, Any]) -> str | None:
    for field in ("start_date", "start_date_time", "date"):
        value = str(row.get(field) or "")
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            return value[:10]
    return None


def parks_location_text(row: dict[str, Any]) -> str:
    values: list[Any] = [
        row.get("display_location"),
        row.get("location"),
        row.get("description"),
    ]
    park_names = row.get("park_names")
    if isinstance(park_names, list):
        values.extend(park_names)
    return " | ".join(str(value).strip() for value in values if str(value or "").strip())


def parks_evidence(
    row: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    lat = row.get("lat") if row.get("lat") is not None else row.get("latitude")
    lng = row.get("lng") if row.get("lng") is not None else row.get("longitude")
    if not valid_nyc_lat_lng(lat, lng):
        return None
    latitude = float(lat)
    longitude = float(lng)
    borough = borough_for_point(boundaries, latitude, longitude)
    day = parks_event_date(row)
    if not borough or not day:
        return None
    return {
        "canonical_id": f"nyc-parks-bigapps-events:{row.get('source_event_id') or 'missing'}@{day}",
        "title": row.get("title"),
        "date": day,
        "location": parks_location_text(row),
        "borough": borough,
        "latitude": latitude,
        "longitude": longitude,
        "source_kind": "nyc_parks_bigapps_events_snapshot",
        "source_event_id": row.get("source_event_id"),
        "source_url": row.get("link"),
        "park_ids": row.get("park_ids"),
    }


def build_index(
    parks_events: list[dict[str, Any]],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in parks_events:
        evidence = parks_evidence(row, boundaries=boundaries)
        if not evidence:
            continue
        key = (title_key(evidence.get("title")), str(evidence.get("date") or ""))
        if key[0] and key[1]:
            index[key].append(evidence)
    return index


def resolve_one(
    proposal: dict[str, Any],
    evidence_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if proposal.get("disposition") != "unresolved":
        return None
    title = title_key(proposal.get("title"))
    day = str(proposal.get("date") or "")
    target_tokens = semantic_location_tokens(proposal.get("location"))
    if not title or not day or not target_tokens:
        return None

    candidates = evidence_index.get((title, day), [])
    scored: list[tuple[int, float, dict[str, Any]]] = []
    for row in candidates:
        evidence_tokens = semantic_location_tokens(row.get("location"))
        overlap = target_tokens.intersection(evidence_tokens)
        if not overlap:
            continue
        score = len(overlap)
        coverage = score / max(1, len(target_tokens))
        scored.append((score, coverage, row))
    if not scored:
        return None

    best_score = max(score for score, _, _ in scored)
    best_coverage = max(coverage for score, coverage, _ in scored if score == best_score)
    winners = [
        row
        for score, coverage, row in scored
        if score == best_score and abs(coverage - best_coverage) < 1e-12
    ]
    representative, diameter = safe_cluster(winners)
    if representative is None:
        return None

    out = dict(proposal)
    out.update(
        {
            "disposition": "mapped_from_nyc_parks_counterpart",
            "proposed_borough": representative["borough"],
            "proposed_latitude": representative["latitude"],
            "proposed_longitude": representative["longitude"],
            "pin_eligible": True,
            "confidence": "high" if diameter <= 35.0 else "medium",
            "reason": (
                "Exact normalized title and date match the committed NYC Parks event snapshot; "
                "distinctive location tokens agree and all winning coordinates form one official borough cluster."
            ),
            "parks_counterpart_evidence_ids": [
                row.get("canonical_id") for row in winners if row.get("canonical_id")
            ],
            "parks_counterpart_source_event_ids": [
                row.get("source_event_id") for row in winners if row.get("source_event_id")
            ],
            "parks_counterpart_source_urls": [
                row.get("source_url") for row in winners if row.get("source_url")
            ],
            "parks_counterpart_cluster_diameter_m": round(diameter, 1),
            "parks_counterpart_location_overlap_score": best_score,
            "parks_counterpart_target_token_coverage": round(best_coverage, 4),
            "evidence_source": "nyc_parks_bigapps_events_snapshot_plus_dcp_borough_boundary",
            "official_boundary_borough": representative["borough"],
        }
    )
    return out


def refine_payload(
    report: dict[str, Any],
    payload: dict[str, Any],
    parks_events: list[dict[str, Any]],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
    parks_snapshot_path: Path = PARKS_SNAPSHOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    before = sum(1 for item in proposals if item.get("disposition") == "unresolved")
    evidence_index = build_index(parks_events, boundaries=boundaries)
    changed = 0
    updated: list[dict[str, Any]] = []
    for proposal in proposals:
        resolved = resolve_one(proposal, evidence_index)
        if resolved is None:
            updated.append(proposal)
        else:
            updated.append(resolved)
            changed += 1

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in updated)
    target = int(report.get("target_null_borough_count") or len(updated))
    unresolved_after = counts.get("unresolved", 0)
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_parks_counterpart",
            "generated_at_utc": utc_now(),
            "accounted_count": len(updated),
            "location_classified_count": sum(1 for item in updated if item.get("location_classified") is True),
            "location_classified_pct": round((len(updated) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in updated if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1
                for item in updated
                if valid_nyc_lat_lng(item.get("proposed_latitude"), item.get("proposed_longitude"))
            ),
            "unresolved_count": unresolved_after,
            "zero_silent_null_borough_records": len(updated) == target,
            "qa_pass": len(updated) == target and all(item.get("disposition") for item in updated),
            "parks_counterpart_refinement": {
                "method": "exact_title_date_distinctive_location_dcp_cluster_v1",
                "parks_snapshot_path": str(parks_snapshot_path),
                "parks_event_count": len(parks_events),
                "indexed_title_date_count": len(evidence_index),
                "unresolved_before": before,
                "unresolved_after": unresolved_after,
                "newly_resolved_count": changed,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_parks_counterpart",
            "generated_at_utc": final_report["generated_at_utc"],
            "target_count": target,
            "proposals": updated,
        }
    )
    return final_report, final_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--input-proposals", type=Path, required=True)
    parser.add_argument("--parks-snapshot", type=Path, default=PARKS_SNAPSHOT)
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    parks_events = load_parks_events(args.parks_snapshot)
    boundaries = load_boundaries(args.borough_boundaries)
    final_report, final_payload = refine_payload(
        report,
        payload,
        parks_events,
        boundaries=boundaries,
        parks_snapshot_path=args.parks_snapshot,
    )
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
