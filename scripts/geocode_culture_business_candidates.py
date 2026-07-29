#!/usr/bin/env python3
"""Geocode Culture business candidates with Enigma's NYC GeoSearch (staging only).

This lets Enigma's geocoder natively process the Culture Business Discovery
candidate format produced by Borg (``nycif-data-pipeline`` →
``culture/pipeline/geocode_candidates.py`` → ``location-candidates.json``), so
there is ONE geocoder, not two.

It reuses the existing Enigma geocoder helpers (``geosearch`` and
``pick_best_result`` from ``geocode_unfilled_gps_proposals``), which enforce the
NYC bounds + confidence discipline. Output is a staging proposals file for
MANUAL REVIEW: nothing is auto-promoted (``promotion_allowed`` false,
``manual_review_status`` "pending", ``approved`` false). A reviewer copies
approved rows back into Borg's
``culture/sample_sources/geocoded_locations.sample.json``.

Usage:
    python3 scripts/geocode_culture_business_candidates.py \
        --input path/to/location-candidates.json \
        --output data/culture_business_geosearch_proposals.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:  # support both `scripts.` and bare imports, like the sibling geocoder
    from scripts.geocode_unfilled_gps_proposals import (
        borough_label,
        geosearch,
        pick_best_result,
    )
except ModuleNotFoundError:  # pragma: no cover
    from geocode_unfilled_gps_proposals import (  # type: ignore
        borough_label,
        geosearch,
        pick_best_result,
    )

GEOCODER_SOURCE = "nyc_geosearch_planninglabs"


def build_query(candidate: dict[str, Any]) -> str:
    address = str(candidate.get("address") or "").strip()
    borough = borough_label(str(candidate.get("borough") or ""))
    if borough and borough.lower() not in address.lower():
        return f"{address}, {borough}, NY"
    return address


def propose_for_candidate(
    candidate: dict[str, Any],
    geosearch_fn: Callable[[str], list[dict[str, Any]]] = geosearch,
) -> dict[str, Any]:
    query = build_query(candidate)
    best = pick_best_result(geosearch_fn(query)) if query else None
    proposal = {
        "candidate_id": candidate.get("candidate_id"),
        "license_id": candidate.get("license_id"),
        "business_id": candidate.get("business_id"),
        "business_name": candidate.get("business_name"),
        "address": candidate.get("address"),
        "borough": candidate.get("borough"),
        "community_district": candidate.get("community_district"),
        "query_used": query,
        # Staging discipline (same as the sibling Enigma geocoder): never auto-applied.
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "approved": False,
    }
    if best:
        proposal.update(
            {
                "geocoder": GEOCODER_SOURCE,
                "geosearch_label": best.get("label"),
                "lat": best.get("lat"),
                "lng": best.get("lng"),
                "confidence": best.get("confidence"),
                "geocoding_status": "proposed_needs_review",
            }
        )
    else:
        proposal["geocoding_status"] = "unresolved_no_confident_match"
    return proposal


def geocode_culture_candidates(
    candidates: list[dict[str, Any]],
    geosearch_fn: Callable[[str], list[dict[str, Any]]] = geosearch,
) -> list[dict[str, Any]]:
    return [propose_for_candidate(c, geosearch_fn) for c in candidates]


def _load_candidates(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("candidates") or []
    return payload if isinstance(payload, list) else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Culture location-candidates.json")
    parser.add_argument("--output", required=True, help="Proposals output path (staging only)")
    args = parser.parse_args(argv)

    candidates = _load_candidates(Path(args.input))
    proposals = geocode_culture_candidates(candidates)
    resolved = sum(1 for p in proposals if p["geocoding_status"] == "proposed_needs_review")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "geocoder": GEOCODER_SOURCE,
                "geosearch_endpoint": "https://geosearch.planninglabs.nyc/v2/search",
                "public_safe": False,
                "policy": "Staging only. Proposals require manual approval before promotion; "
                "copy approved rows into nycif-data-pipeline "
                "culture/sample_sources/geocoded_locations.sample.json.",
                "candidate_count": len(candidates),
                "resolved_count": resolved,
                "proposals": proposals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Culture geocode: {resolved}/{len(candidates)} resolved (pending manual review) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
