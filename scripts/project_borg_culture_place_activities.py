#!/usr/bin/env python3
"""Project Culture place activity candidates through the evidence gate.

This projector never classifies a place as Culture. It consumes already-accepted
Culture places and activity candidates, then emits exactly one terminal
disposition for every candidate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "nycif.borg-culture-place-activity-projection.v1"
APPROVED_SOURCES = {
    "HOST_FIRST_PARTY",
    "OFFICIAL_ORGANIZER",
    "OFFICIAL_VENUE",
    "VERIFIED_PARTNER_WITH_HOST_CONFIRMATION",
}
PUBLIC_STATES = {"CURRENT", "FUTURE", "ONGOING"}


def _index_places(places: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for place in places:
        bid = str(place.get("business_id") or "")
        lid = str(place.get("location_id") or "")
        if not bid or not lid:
            continue
        if place.get("disposition") != "ACCEPTED":
            continue
        if not place.get("why_included"):
            continue
        if place.get("independent_culture_evidence") is not True:
            continue
        out[(bid, lid)] = place
    return out


def project(*, places: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = _index_places(places)
    seen: set[str] = set()
    records: list[dict[str, Any]] = []

    for candidate in candidates:
        cid = str(candidate.get("candidate_id") or "")
        if not cid:
            raise ValueError("candidate_id required")
        if cid in seen:
            raise ValueError(f"duplicate candidate_id: {cid}")
        seen.add(cid)

        bid = str(candidate.get("host_business_id") or "")
        lid = str(candidate.get("host_location_id") or "")
        state = str(candidate.get("activity_state") or "UNKNOWN")
        kind = str(candidate.get("activity_kind") or "")
        source_class = str(candidate.get("source_class") or "")
        relation = str(candidate.get("host_relation_evidence_state") or "")
        location_state = str(candidate.get("location_state") or "")

        disposition = "CULTURE_ACTIVITY_REVIEW_REQUIRED"
        public = False
        map_eligible = False
        reason = "evidence_gate_incomplete"

        if (bid, lid) not in accepted:
            disposition = "NOT_CULTURE_ACTIVITY"
            reason = "host_not_accepted_culture_place"
        elif state == "CANCELLED":
            disposition = "CULTURE_ACTIVITY_CANCELLED"
            reason = "cancelled"
        elif state == "EXPIRED":
            disposition = "CULTURE_ACTIVITY_EXPIRED"
            reason = "expired"
        elif relation != "CONFIRMED":
            reason = "host_relation_unconfirmed"
        elif source_class not in APPROVED_SOURCES:
            reason = "source_not_approved"
        elif state not in PUBLIC_STATES:
            reason = "activity_state_not_public"
        elif kind == "DATED_OCCURRENCE" and not candidate.get("occurrence_id"):
            reason = "canonical_occurrence_id_required"
        elif kind == "ONGOING_PROGRAM" and not candidate.get("program_id"):
            reason = "stable_program_id_required"
        elif kind not in {"DATED_OCCURRENCE", "ONGOING_PROGRAM"}:
            reason = "unsupported_activity_kind"
        elif location_state in {"AMBIGUOUS", "REVIEW_REQUIRED", "UNRESOLVED"}:
            disposition = "CULTURE_ACTIVITY_LIST_ONLY_LOCATION_PENDING"
            public = True
            reason = "location_pending"
        elif location_state in {"EXACT_STOREFRONT", "APPROVED_GEOCODE", "RESOLVED"}:
            disposition = "CULTURE_ACTIVITY_PUBLIC"
            public = True
            map_eligible = True
            reason = "eligible"
        else:
            reason = "location_state_not_approved"

        records.append({
            "candidate_id": cid,
            "host_business_id": bid,
            "host_location_id": lid,
            "title": candidate.get("title"),
            "activity_kind": kind,
            "activity_state": state,
            "occurrence_id": candidate.get("occurrence_id"),
            "program_id": candidate.get("program_id"),
            "source_class": source_class,
            "terminal_disposition": disposition,
            "public": public,
            "map_eligible": map_eligible,
            "reason": reason,
        })

    terminal = len(records)
    if terminal != len(candidates):
        raise AssertionError("silent loss")

    return {
        "schema": SCHEMA,
        "records": records,
        "accounting": {
            "input_candidates": len(candidates),
            "terminal_records": terminal,
            "public_records": sum(1 for r in records if r["public"]),
            "map_records": sum(1 for r in records if r["map_eligible"]),
            "silent_loss": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--places", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    places_payload = json.loads(Path(args.places).read_text())
    candidates_payload = json.loads(Path(args.candidates).read_text())
    result = project(
        places=places_payload.get("places") or places_payload.get("records") or [],
        candidates=candidates_payload.get("candidates") or candidates_payload.get("records") or [],
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
