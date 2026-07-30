#!/usr/bin/env python3
"""Apply only the Stage 8 proposals proven to match one upstream occurrence."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stage8_match_supported_coordinate_proposals import (
    PROPOSALS,
    ROOT,
    TARGET,
    candidate_rows,
    dataset,
    day,
    load,
    location,
    norm,
    source_id,
    valid_nyc if False else norm,
)

REPORT = ROOT / "data" / "reports" / "stage8_supported_coordinate_apply_report.json"


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def valid_coordinate(lat: Any, lng: Any) -> bool:
    try:
        latf = float(lat)
        lngf = float(lng)
    except (TypeError, ValueError):
        return False
    return 40.45 <= latf <= 40.95 and -74.30 <= lngf <= -73.65


def main() -> int:
    if str(os.environ.get("NYCIF_STAGE8_APPLY") or "").lower() not in {"1", "true", "yes"}:
        raise RuntimeError("NYCIF_STAGE8_APPLY=1 is required")

    proposals_payload = load(PROPOSALS)
    proposals = proposals_payload.get("proposals") if isinstance(proposals_payload, dict) else []
    if not isinstance(proposals, list) or not proposals:
        raise RuntimeError("non-empty proposal artifact required")

    target_payload = load(TARGET)
    target_rows = candidate_rows(target_payload)
    before_count = len(target_rows)
    applied = []

    for proposal in proposals:
        ds = norm(proposal.get("source"))
        sid = norm(proposal.get("source_event_id"))
        proposal_day = str(proposal.get("date") or "")[:10]
        proposal_location = norm(proposal.get("location"))
        candidates = [
            row
            for row in target_rows
            if norm(dataset(row)) == ds
            and norm(source_id(row)) == sid
            and (not proposal_day or day(row) == proposal_day)
        ]
        if len(candidates) != 1 and proposal_location:
            candidates = [row for row in candidates if norm(location(row)) == proposal_location]
        if len(candidates) != 1:
            raise RuntimeError(
                f"proposal {proposal.get('canonical_id')} expected one upstream row; found {len(candidates)}"
            )
        if not valid_coordinate(proposal.get("lat"), proposal.get("lng")):
            raise RuntimeError(f"invalid proposal coordinate: {proposal.get('canonical_id')}")

        row = candidates[0]
        before = {
            "lat": row.get("lat", row.get("latitude")),
            "lng": row.get("lng", row.get("longitude")),
            "borough": row.get("borough") or row.get("event_borough"),
            "match_type": row.get("match_type"),
            "location_source": row.get("location_source"),
        }
        lat = float(proposal["lat"])
        lng = float(proposal["lng"])
        row["lat"] = lat
        row["lng"] = lng
        row["latitude"] = lat
        row["longitude"] = lng
        row["borough"] = proposal["borough"]
        if "event_borough" in row:
            row["event_borough"] = proposal["borough"]
        row["match_type"] = "stage8_same_snapshot_precedent"
        row["location_source"] = "stage8_same_snapshot_precedent"
        row["geocoder_source"] = "stage8_same_snapshot_precedent"
        row["geocoder_confidence"] = "high"
        row["confidence_reason"] = (
            "Stage 8 exact same-snapshot certified precedent; "
            f"method={proposal.get('method')}; evidence={','.join(proposal.get('evidence_canonical_ids') or [])}"
        )
        row["stage8_coordinate_resolution"] = {
            "method": proposal.get("method"),
            "fingerprint_sha256": proposal.get("fingerprint_sha256"),
            "evidence_canonical_ids": proposal.get("evidence_canonical_ids") or [],
        }
        applied.append(
            {
                "canonical_id": proposal.get("canonical_id"),
                "source": proposal.get("source"),
                "source_event_id": proposal.get("source_event_id"),
                "date": proposal.get("date"),
                "before": before,
                "after": {
                    "lat": lat,
                    "lng": lng,
                    "borough": proposal.get("borough"),
                    "match_type": row["match_type"],
                    "location_source": row["location_source"],
                },
                "method": proposal.get("method"),
                "evidence_canonical_ids": proposal.get("evidence_canonical_ids") or [],
            }
        )

    write(TARGET, target_payload)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "artifact_type": "stage8_supported_coordinate_apply_report",
        "schema_version": "1.0.0",
        "generated_at_utc": now,
        "target_path": str(TARGET.relative_to(ROOT)),
        "target_candidate_rows_before": before_count,
        "proposal_total": len(proposals),
        "applied_total": len(applied),
        "all_proposals_applied_exactly_once": len(applied) == len(proposals),
        "raw_official_snapshots_modified": False,
        "qa_pass": len(applied) == len(proposals),
        "applied": applied,
    }
    write(REPORT, report)
    print(json.dumps({key: value for key, value in report.items() if key != "applied"}, indent=2, sort_keys=True))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
