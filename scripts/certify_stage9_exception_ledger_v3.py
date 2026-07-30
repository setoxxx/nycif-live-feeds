#!/usr/bin/env python3
"""Run the Stage 9 certificate against the projector-emitted canonical set."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import certify_stage9_exception_ledger_v2 as certificate

ACCEPTED = certificate.DATA / "events_discovery_accepted_canonical_v02.json"


def authoritative_population(
    approved: list[dict[str, Any]], review: list[dict[str, Any]], expected: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    payload = certificate.load(ACCEPTED)
    accepted = certificate.rows(payload)
    if len(accepted) != expected:
        raise RuntimeError(f"authoritative accepted population mismatch: expected {expected}, got {len(accepted)}")
    ids = [certificate.cid(row) for row in accepted]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("authoritative accepted population has missing or duplicate canonical IDs")
    return accepted, {
        "method": "projector_emitted_pre_split_population",
        "accepted_canonical_artifact_count": len(accepted),
        "approved_projection_count": len(approved),
        "review_projection_count": len(review),
        "projection_union_not_used_for_canonical_membership": True,
    }


certificate.canonical_population = authoritative_population

if __name__ == "__main__":
    raise SystemExit(certificate.main())
