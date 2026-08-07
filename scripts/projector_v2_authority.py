#!/usr/bin/env python3
"""Shared semantic authority adapter for the discovery projector V2 cutover.

This module intentionally does not redefine occurrence identity, rejection scope,
or exact-pin evidence rules. It delegates those decisions to the canonical
OccurrenceIdentityV2 and pin-integrity authorities so the projector has one
narrow integration surface.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from occurrence_identity_contract import (  # noqa: E402
    identity_precision,
    occurrence_key_v2,
    occurrence_key_v2_set,
    rejection_identity_sets,
    rejection_matches,
)
from pin_integrity import evaluate_map_eligibility  # noqa: E402


@dataclass(frozen=True)
class RejectionContract:
    exact: frozenset[tuple[str, str, str]]
    days: frozenset[tuple[str, str, str]]
    sources: frozenset[tuple[str, str]]


def occurrence_identity_v2(row: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical V2 identity without inventing missing precision."""
    precision = identity_precision(row)
    key = occurrence_key_v2(row)
    return {
        "key": key,
        "precision": precision,
        "identity_ambiguous": precision == "AMBIGUOUS",
    }


def occurrence_identity_v2_set(rows: Iterable[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return occurrence_key_v2_set(list(rows))


def build_rejection_contract(rows: Iterable[dict[str, Any]]) -> RejectionContract:
    exact, days, sources = rejection_identity_sets(list(rows))
    return RejectionContract(
        exact=frozenset(exact),
        days=frozenset(days),
        sources=frozenset(sources),
    )


def rejection_applies(row: dict[str, Any], contract: RejectionContract) -> bool:
    return rejection_matches(
        row,
        rejected_exact=set(contract.exact),
        rejected_days=set(contract.days),
        rejected_sources=set(contract.sources),
    )


def general_area_label(row: dict[str, Any]) -> str | None:
    """Return a generalized display label without promoting an exact venue."""
    for key in ("general_area_label", "neighborhood", "borough"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    for key in ("general_area_label", "neighborhood", "borough"):
        value = nycif.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def semantic_map_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical map state for projector integration.

    Exact coordinates are returned only for shared-authority MAP_READY. All
    other states fail closed. GENERAL_AREA includes only a generalized label.
    """
    decision = evaluate_map_eligibility(row)
    state = str(decision.get("map_eligibility") or "REVIEW_REQUIRED")
    exact = state == "MAP_READY" and decision.get("exact_pin_eligible") is True

    return {
        "map_eligibility_state": state,
        "exact_pin_eligible": exact,
        "geometry_valid": bool(decision.get("geometry_valid")),
        "reason_code": decision.get("reason_code"),
        "latitude": decision.get("normalized_lat") if exact else None,
        "longitude": decision.get("normalized_lng") if exact else None,
        "general_area_label": general_area_label(row) if state == "GENERAL_AREA" else None,
        "coordinate_status": "map_ready" if exact else "list_only",
        "certified_pin": exact,
    }


def projector_authority_summary(
    rows: Iterable[dict[str, Any]],
    rejection_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Produce deterministic audit counts for projector migration QA."""
    source_rows = list(rows)
    contract = build_rejection_contract(rejection_rows)
    identities = [occurrence_identity_v2(row) for row in source_rows]
    map_decisions = [semantic_map_decision(row) for row in source_rows]

    return {
        "row_count": len(source_rows),
        "identity_ambiguous_count": sum(1 for item in identities if item["identity_ambiguous"]),
        "unique_non_ambiguous_occurrence_count": len(occurrence_identity_v2_set(source_rows)),
        "rejected_row_count": sum(1 for row in source_rows if rejection_applies(row, contract)),
        "map_state_counts": {
            state: sum(1 for item in map_decisions if item["map_eligibility_state"] == state)
            for state in ("MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY")
        },
        "unsupported_exact_pin_count": sum(
            1
            for item in map_decisions
            if item["latitude"] is not None
            and not (item["map_eligibility_state"] == "MAP_READY" and item["certified_pin"] is True)
        ),
    }
