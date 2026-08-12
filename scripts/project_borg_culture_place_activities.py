#!/usr/bin/env python3
"""Project Culture place activity candidates through the evidence gate.

This projector never classifies a place as Culture. It consumes already-accepted
Culture places and activity candidates, then emits exactly one terminal
disposition for every candidate.
"""
from __future__ import annotations

import argparse
from typing import Any

from scripts.borg_cli_paths import read_workspace_json, write_workspace_json

SCHEMA = "nycif.borg-culture-place-activity-projection.v1"
APPROVED_SOURCES = {
    "HOST_FIRST_PARTY",
    "OFFICIAL_ORGANIZER",
    "OFFICIAL_VENUE",
    "VERIFIED_PARTNER_WITH_HOST_CONFIRMATION",
}
PUBLIC_STATES = {"CURRENT", "FUTURE", "ONGOING"}
PENDING_LOCATION_STATES = {"AMBIGUOUS", "REVIEW_REQUIRED", "UNRESOLVED"}
APPROVED_LOCATION_STATES = {"EXACT_STOREFRONT", "APPROVED_GEOCODE", "RESOLVED"}
REVIEW = "CULTURE_ACTIVITY_REVIEW_REQUIRED"


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


def _candidate_identity(candidate: dict[str, Any], seen: set[str]) -> str:
    cid = str(candidate.get("candidate_id") or "")
    if not cid:
        raise ValueError("candidate_id required")
    if cid in seen:
        raise ValueError(f"duplicate candidate_id: {cid}")
    seen.add(cid)
    return cid


def _authority_state_gate(
    candidate: dict[str, Any],
    accepted: dict[tuple[str, str], dict[str, Any]],
) -> tuple[str, bool, bool, str] | None:
    bid = str(candidate.get("host_business_id") or "")
    lid = str(candidate.get("host_location_id") or "")
    state = str(candidate.get("activity_state") or "UNKNOWN")
    relation = str(candidate.get("host_relation_evidence_state") or "")
    source_class = str(candidate.get("source_class") or "")

    if (bid, lid) not in accepted:
        return "NOT_CULTURE_ACTIVITY", False, False, "host_not_accepted_culture_place"
    if state == "CANCELLED":
        return "CULTURE_ACTIVITY_CANCELLED", False, False, "cancelled"
    if state == "EXPIRED":
        return "CULTURE_ACTIVITY_EXPIRED", False, False, "expired"
    if relation != "CONFIRMED":
        return REVIEW, False, False, "host_relation_unconfirmed"
    if source_class not in APPROVED_SOURCES:
        return REVIEW, False, False, "source_not_approved"
    if state not in PUBLIC_STATES:
        return REVIEW, False, False, "activity_state_not_public"
    return None


def _identity_gate(candidate: dict[str, Any]) -> tuple[str, bool, bool, str] | None:
    kind = str(candidate.get("activity_kind") or "")
    if kind == "DATED_OCCURRENCE":
        if not candidate.get("occurrence_id"):
            return REVIEW, False, False, "canonical_occurrence_id_required"
        return None
    if kind == "ONGOING_PROGRAM":
        if not candidate.get("program_id"):
            return REVIEW, False, False, "stable_program_id_required"
        return None
    return REVIEW, False, False, "unsupported_activity_kind"


def _location_gate(candidate: dict[str, Any]) -> tuple[str, bool, bool, str]:
    location_state = str(candidate.get("location_state") or "")
    if location_state in PENDING_LOCATION_STATES:
        return "CULTURE_ACTIVITY_LIST_ONLY_LOCATION_PENDING", True, False, "location_pending"
    if location_state in APPROVED_LOCATION_STATES:
        return "CULTURE_ACTIVITY_PUBLIC", True, True, "eligible"
    return REVIEW, False, False, "location_state_not_approved"


def _evaluate_candidate(
    candidate: dict[str, Any],
    accepted: dict[tuple[str, str], dict[str, Any]],
) -> tuple[str, bool, bool, str]:
    gate_result = _authority_state_gate(candidate, accepted)
    if gate_result is not None:
        return gate_result
    gate_result = _identity_gate(candidate)
    if gate_result is not None:
        return gate_result
    return _location_gate(candidate)


def _project_record(
    candidate: dict[str, Any],
    cid: str,
    accepted: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    disposition, public, map_eligible, reason = _evaluate_candidate(candidate, accepted)
    return {
        "candidate_id": cid,
        "host_business_id": str(candidate.get("host_business_id") or ""),
        "host_location_id": str(candidate.get("host_location_id") or ""),
        "title": candidate.get("title"),
        "activity_kind": str(candidate.get("activity_kind") or ""),
        "activity_state": str(candidate.get("activity_state") or "UNKNOWN"),
        "occurrence_id": candidate.get("occurrence_id"),
        "program_id": candidate.get("program_id"),
        "source_class": str(candidate.get("source_class") or ""),
        "terminal_disposition": disposition,
        "public": public,
        "map_eligible": map_eligible,
        "reason": reason,
    }


def project(*, places: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = _index_places(places)
    seen: set[str] = set()
    records = [
        _project_record(candidate, _candidate_identity(candidate, seen), accepted)
        for candidate in candidates
    ]
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
    places_payload = read_workspace_json(args.places)
    candidates_payload = read_workspace_json(args.candidates)
    result = project(
        places=places_payload.get("places") or places_payload.get("records") or [],
        candidates=candidates_payload.get("candidates") or candidates_payload.get("records") or [],
    )
    write_workspace_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
