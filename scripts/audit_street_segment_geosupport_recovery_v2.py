#!/usr/bin/env python3
"""Read-only local GeoSupport audit for TVPP street-segment evidence.

This lane evaluates NYC Planning Geosupport as an authoritative *evidence source*
for unresolved ``MAIN between CROSS1 and CROSS2`` claims without requiring
Geoclient API credentials.

Important safety boundary:
- this audit never mutates location caches or public feeds;
- it never grants publication authority;
- it never marks a result exact-pin eligible;
- a candidate survives only when both stated intersections resolve uniquely,
  Function 2/2W coordinates are borough-valid, Function 3 resolves the claimed
  blockface, and its endpoint node pair agrees with the two intersections.

The Python binding is intentionally optional at import time so unit tests can
run with a fake backend. The live audit executes inside NYC Planning's published
``nycplanning/docker-geosupport`` runtime, which includes Geosupport and the
python-geosupport binding. The container is an evidence runtime only; it does
not become Projector or publication authority.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.audit_street_segment_geoclient_recovery import current_segment_claims
    from scripts.nyc_clock import nyc_today_iso
    from scripts.nyc_location_resolver import (
        coordinate_matches_borough,
        haversine_m,
        parse_street_between,
    )
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.sync_nyc_open_data import fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from audit_street_segment_geoclient_recovery import current_segment_claims
    from nyc_clock import nyc_today_iso
    from nyc_location_resolver import coordinate_matches_borough, haversine_m, parse_street_between
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from sync_nyc_open_data import fetch_raw_rows

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2"
EVIDENCE_CLASS = "NYC_PLANNING_GEOSUPPORT_STREET_SEGMENT_NONPUBLIC"
GEOSUPPORT_RUNTIME_REPOSITORY = "NYCPlanning/data-engineering"
GEOSUPPORT_RUNTIME_SOURCE_PATH = "admin/run_environment/docker/docker-geosupport"
GEOSUPPORT_RUNTIME_SOURCE_COMMIT = "fe4225182844c3431ddc6c08dcae82fe9187f8fc"
DEFAULT_GEOSUPPORT_RUNTIME_IMAGE = "nycplanning/docker-geosupport:26.2.0"

BOROUGH_CODES = {
    "manhattan": "MN",
    "new york": "MN",
    "mn": "MN",
    "bronx": "BX",
    "bx": "BX",
    "brooklyn": "BK",
    "bk": "BK",
    "queens": "QN",
    "qn": "QN",
    "staten island": "SI",
    "si": "SI",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def borough_code(value: Any) -> str | None:
    return BOROUGH_CODES.get(_norm(value))


def _clean_node(value: Any) -> str:
    return str(value or "").strip()


def _parse_coordinate(value: Any) -> float | None:
    try:
        parsed = float(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed


class GeoSupportStreetEvidence:
    """Strict wrapper around a python-geosupport-compatible backend."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.call_count = 0

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        result = self.backend.call(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GeoSupport returned a non-dict result")
        return result

    def resolve_intersection(
        self,
        *,
        main_street: str,
        cross_street: str,
        borough: str,
    ) -> tuple[dict[str, Any] | None, str]:
        code = borough_code(borough)
        if code is None:
            return None, "BOROUGH_UNSUPPORTED"

        try:
            base = self._call(
                {
                    "function": 2,
                    "borough_code": code,
                    "street_name": main_street,
                    "street_name_2": cross_street,
                }
            )
        except Exception:
            # Function 2 fails for unresolved/ambiguous multiple intersections;
            # ambiguity is a hard stop in this evidence lane.
            return None, "INTERSECTION_UNRESOLVED_OR_AMBIGUOUS"

        node = _clean_node(base.get("LION Node Number"))
        if not node:
            return None, "INTERSECTION_NODE_MISSING"

        try:
            detail = self._call({"function": "2W", "node": node})
        except Exception:
            return None, "INTERSECTION_NODE_DETAIL_FAILED"

        lat = _parse_coordinate(detail.get("Latitude"))
        lng = _parse_coordinate(detail.get("Longitude"))
        if lat is None or lng is None or not valid_nyc_lat_lng(lat, lng):
            return None, "INTERSECTION_COORDINATE_INVALID"
        if not coordinate_matches_borough(lat, lng, borough):
            return None, "INTERSECTION_BOROUGH_CONTRADICTION"

        return (
            {
                "node": node,
                "latitude": lat,
                "longitude": lng,
                "number_of_intersecting_streets": str(
                    base.get("Number of Intersecting Streets") or ""
                ).strip(),
                "main_street": main_street,
                "cross_street": cross_street,
            },
            "INTERSECTION_RESOLVED",
        )

    def resolve_segment(self, claim: dict[str, Any]) -> dict[str, Any]:
        display = str(claim.get("event_location") or "").strip()
        borough = str(claim.get("borough") or "").strip()
        parsed = parse_street_between(display)
        if not parsed:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "NOT_STREET_BETWEEN_CLAIM",
            }

        main_street, cross1, cross2 = parsed
        first, first_reason = self.resolve_intersection(
            main_street=main_street,
            cross_street=cross1,
            borough=borough,
        )
        if first is None:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": first_reason,
                "failed_endpoint": "cross1",
            }

        second, second_reason = self.resolve_intersection(
            main_street=main_street,
            cross_street=cross2,
            borough=borough,
        )
        if second is None:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": second_reason,
                "failed_endpoint": "cross2",
                "endpoint_1": first,
            }

        if first["node"] == second["node"]:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "SEGMENT_ENDPOINTS_COLLAPSE_TO_ONE_NODE",
                "endpoint_1": first,
                "endpoint_2": second,
            }

        code = borough_code(borough)
        if code is None:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "BOROUGH_UNSUPPORTED",
                "endpoint_1": first,
                "endpoint_2": second,
            }

        try:
            segment = self._call(
                {
                    "function": 3,
                    "borough_code": code,
                    "on": main_street,
                    "from": cross1,
                    "to": cross2,
                    "mode_switch": "X",
                }
            )
        except Exception:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "SEGMENT_FUNCTION_3_UNRESOLVED",
                "endpoint_1": first,
                "endpoint_2": second,
            }

        from_node = _clean_node(segment.get("From Node"))
        to_node = _clean_node(segment.get("To Node"))
        expected_nodes = {first["node"], second["node"]}
        segment_nodes = {from_node, to_node}
        if not from_node or not to_node or segment_nodes != expected_nodes:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "SEGMENT_NODE_PAIR_MISMATCH",
                "endpoint_1": first,
                "endpoint_2": second,
                "function_3_from_node": from_node,
                "function_3_to_node": to_node,
            }

        distance_m = haversine_m(
            first["latitude"],
            first["longitude"],
            second["latitude"],
            second["longitude"],
        )
        if not 20.0 <= distance_m <= 5000.0:
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "SEGMENT_DISTANCE_OUT_OF_RANGE",
                "endpoint_1": first,
                "endpoint_2": second,
                "distance_m": round(distance_m, 2),
            }

        midpoint_lat = round((first["latitude"] + second["latitude"]) / 2.0, 7)
        midpoint_lng = round((first["longitude"] + second["longitude"]) / 2.0, 7)
        if not coordinate_matches_borough(midpoint_lat, midpoint_lng, borough):
            return {
                "strict_nonpublic_segment_evidence": False,
                "reason_code": "SEGMENT_MIDPOINT_BOROUGH_CONTRADICTION",
                "endpoint_1": first,
                "endpoint_2": second,
            }

        return {
            "strict_nonpublic_segment_evidence": True,
            "reason_code": "GEOSUPPORT_ENDPOINTS_AND_SEGMENT_NODES_AGREE",
            "evidence_class": EVIDENCE_CLASS,
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "publication_allowed": False,
            "exact_pin_eligible": False,
            "projector_consumed": False,
            "endpoint_1": first,
            "endpoint_2": second,
            "function_3_from_node": from_node,
            "function_3_to_node": to_node,
            "function_3_segment_ids": segment.get("Segment IDs") or [],
            "distance_m": round(distance_m, 2),
            "candidate_midpoint": {
                "latitude": midpoint_lat,
                "longitude": midpoint_lng,
                "generated_for_nonpublic_audit_only": True,
            },
        }


def audit_claims(
    claims: dict[str, dict[str, Any]],
    evidence: GeoSupportStreetEvidence,
    *,
    max_claims: int = 5000,
) -> dict[str, Any]:
    if len(claims) > max_claims:
        raise RuntimeError(
            f"unique street-segment claim count exceeds safety cap: {len(claims)} > {max_claims}"
        )

    rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    strict_count = 0
    occurrence_coverage = 0

    for key in sorted(claims):
        claim = claims[key]
        result = evidence.resolve_segment(claim)
        strict = result.get("strict_nonpublic_segment_evidence") is True
        reason = str(result.get("reason_code") or "UNSPECIFIED")
        reason_counts[reason] += 1
        if strict:
            strict_count += 1
            occurrence_coverage += int(claim.get("occurrence_count") or 0)
        rows.append(
            {
                **claim,
                "claim_key": key,
                **result,
            }
        )

    runtime_image = os.environ.get(
        "GEOSUPPORT_RUNTIME_IMAGE", DEFAULT_GEOSUPPORT_RUNTIME_IMAGE
    ).strip() or DEFAULT_GEOSUPPORT_RUNTIME_IMAGE
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_authority": "NYC Planning Geosupport Desktop Edition",
        "geosupport_runtime_repository": GEOSUPPORT_RUNTIME_REPOSITORY,
        "geosupport_runtime_source_path": GEOSUPPORT_RUNTIME_SOURCE_PATH,
        "geosupport_runtime_source_commit": GEOSUPPORT_RUNTIME_SOURCE_COMMIT,
        "geosupport_runtime_image": runtime_image,
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "projector_consumed": False,
        "unique_segment_claim_count": len(claims),
        "strict_nonpublic_segment_evidence_count": strict_count,
        "strict_nonpublic_occurrence_coverage": occurrence_coverage,
        "unresolved_or_blocked_claim_count": len(claims) - strict_count,
        "geosupport_call_count": evidence.call_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "public_map_write_count": 0,
            "location_cache_write_count": 0,
            "projector_consumed_count": 0,
        },
        "claims": rows,
    }


def load_geosupport_backend() -> Any:
    try:
        from geosupport import Geosupport
    except ImportError as exc:  # pragma: no cover - exercised by live workflow
        raise RuntimeError(
            "python-geosupport is not installed; live audit must run inside the approved GeoSupport runtime"
        ) from exc
    return Geosupport()


def build_report(max_claims: int = 5000) -> dict[str, Any]:
    raw_rows = fetch_raw_rows()
    today_nyc = nyc_today_iso()
    claims = current_segment_claims(raw_rows, today_nyc)
    evidence = GeoSupportStreetEvidence(load_geosupport_backend())
    report = audit_claims(claims, evidence, max_claims=max_claims)
    report["raw_rows_loaded"] = len(raw_rows)
    report["today_nyc"] = today_nyc
    report["api_credentials_required"] = False
    report["contract_acceptance_required_before_any_publication"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-claims", type=int, default=5000)
    args = parser.parse_args()

    report = build_report(max_claims=args.max_claims)
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    summary_keys = (
        "schema_version",
        "source_authority",
        "geosupport_runtime_repository",
        "geosupport_runtime_source_commit",
        "geosupport_runtime_image",
        "api_credentials_required",
        "raw_rows_loaded",
        "unique_segment_claim_count",
        "strict_nonpublic_segment_evidence_count",
        "strict_nonpublic_occurrence_coverage",
        "unresolved_or_blocked_claim_count",
        "geosupport_call_count",
        "reason_counts",
        "hard_zero_gates",
    )
    print(json.dumps({key: report[key] for key in summary_keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
