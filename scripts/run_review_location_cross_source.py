#!/usr/bin/env python3
"""Run cross-source review-location refinement with DCP boundary evidence.

The base cross-source engine already requires exact title/date, distinctive
location agreement, one borough, and a tight coordinate cluster. This wrapper
allows an unresolved counterpart that already has coordinates to serve as
location evidence only when those coordinates fall inside exactly one official
NYC Department of City Planning borough polygon.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts import refine_review_location_cross_source as cross
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.resolve_remaining_review_locations import borough_for_point, load_boundaries
except ModuleNotFoundError:  # pragma: no cover
    import refine_review_location_cross_source as cross
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from resolve_remaining_review_locations import borough_for_point, load_boundaries


def evidence_from_proposal_with_boundaries(
    proposal: dict[str, Any],
    boundaries: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    existing = cross.evidence_from_proposal(proposal)
    if existing is not None:
        return existing

    lat = proposal.get("existing_latitude")
    lng = proposal.get("existing_longitude")
    if not valid_nyc_lat_lng(lat, lng):
        return None
    boundary_borough = borough_for_point(boundaries, float(lat), float(lng))
    proposed_borough = cross.canonical_borough(proposal.get("proposed_borough"))
    if not boundary_borough or (proposed_borough and proposed_borough != boundary_borough):
        return None
    return {
        "canonical_id": proposal.get("canonical_id"),
        "title": proposal.get("title"),
        "date": proposal.get("date"),
        "location": proposal.get("location"),
        "borough": boundary_borough,
        "latitude": float(lat),
        "longitude": float(lng),
        "source_kind": "review_existing_coordinate_dcp_boundary_evidence",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--input-proposals", type=Path, required=True)
    parser.add_argument("--approved-manifest", type=Path, default=cross.APPROVED_MANIFEST)
    parser.add_argument("--approved-pages", type=Path, default=cross.APPROVED_PAGES)
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    approved_manifest, approved_events = cross.load_review_events(args.approved_manifest, args.approved_pages)
    source_generated = report.get("source_generated_at_utc")
    approved_generated = approved_manifest.get("generated_at_utc")
    if source_generated and approved_generated and source_generated != approved_generated:
        raise RuntimeError(
            "Approved and review artifacts are not from the same snapshot: "
            f"review={source_generated}, approved={approved_generated}"
        )

    boundaries = load_boundaries(args.borough_boundaries)
    original = cross.evidence_from_proposal

    def boundary_evidence(proposal: dict[str, Any]) -> dict[str, Any] | None:
        # Avoid recursion after monkeypatching the module global.
        direct = original(proposal)
        if direct is not None:
            return direct
        lat = proposal.get("existing_latitude")
        lng = proposal.get("existing_longitude")
        if not valid_nyc_lat_lng(lat, lng):
            return None
        boundary_borough = borough_for_point(boundaries, float(lat), float(lng))
        proposed_borough = cross.canonical_borough(proposal.get("proposed_borough"))
        if not boundary_borough or (proposed_borough and proposed_borough != boundary_borough):
            return None
        return {
            "canonical_id": proposal.get("canonical_id"),
            "title": proposal.get("title"),
            "date": proposal.get("date"),
            "location": proposal.get("location"),
            "borough": boundary_borough,
            "latitude": float(lat),
            "longitude": float(lng),
            "source_kind": "review_existing_coordinate_dcp_boundary_evidence",
        }

    cross.evidence_from_proposal = boundary_evidence
    final_report, final_payload = cross.refine_payload(
        report,
        payload,
        approved_events,
        approved_generated_at_utc=approved_generated,
    )
    final_report["cross_source_refinement"]["official_boundary_coordinate_evidence"] = True
    cross.write_json(args.report, final_report)
    cross.write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
