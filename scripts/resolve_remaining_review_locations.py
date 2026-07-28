#!/usr/bin/env python3
"""Resolve the remaining review-location proposals with official NYC evidence.

Existing coordinates are assigned a borough by point-in-polygon against the
NYC Department of City Planning Borough Boundaries GeoJSON. Coordinate-less
physical locations may be resolved through the existing NYCIF gazetteer and,
when explicitly enabled, temporary NYC GeoSearch calls. Results remain proposal
artifacts only; no cache, feed, WordPress, or public-map write occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.audit_review_location_coverage import BOROUGHS, canonical_borough
    from scripts.nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        load_json,
        valid_nyc_lat_lng,
    )
    from scripts.nyc_location_resolver import NYCLocationResolver
    from scripts.refine_review_location_coverage import location_candidates
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover
    from audit_review_location_coverage import BOROUGHS, canonical_borough
    from nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        load_json,
        valid_nyc_lat_lng,
    )
    from nyc_location_resolver import NYCLocationResolver
    from refine_review_location_coverage import location_candidates
    from schema_v1_common import utc_now

BOUNDARY_SOURCE_URL = "https://data.cityofnewyork.us/api/v3/views/gthc-hcne/query.geojson?accessType=DOWNLOAD"
NON_GEOCODABLE_RE = re.compile(
    r"please see (?:the )?flyer|location (?:tba|to be announced)|check website|"
    r"participating restaurants|locations? (?:vary|varies)|address (?:tba|pending)",
    flags=re.IGNORECASE,
)


def raw_location_candidates(value: Any) -> list[str]:
    text = str(value or "")
    raw_parts = [part.strip() for part in text.split("|") if part.strip()]
    expanded: list[str] = []
    for part in raw_parts:
        expanded.append(part)
        match = re.search(r"\b(?:in|at)\s+(.+)$", part, flags=re.IGNORECASE)
        if match:
            expanded.append(match.group(1).strip())
        for inner in re.findall(r"\((?:in\s+)?([^()]+)\)", part, flags=re.IGNORECASE):
            expanded.append(inner.strip())
    normalized_order = location_candidates(value)
    by_key: dict[str, str] = {}
    for part in expanded:
        key = re.sub(r"[^a-z0-9]+", " ", part.lower()).strip()
        if key and key not in by_key:
            by_key[key] = part
    return [by_key[key] for key in normalized_order if key in by_key]


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 4:
        return False
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        intersects = (y1 > lat) != (y2 > lat)
        if intersects:
            x_at_lat = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-30) + x1
            if lng < x_at_lat:
                inside = not inside
        previous = current
    return inside


def point_in_polygon(lng: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(lng, lat, polygon[0]):
        return False
    return not any(point_in_ring(lng, lat, hole) for hole in polygon[1:])


def geometry_contains(geometry: dict[str, Any], lng: float, lat: float) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return point_in_polygon(lng, lat, coordinates)
    if geometry_type == "MultiPolygon":
        return any(point_in_polygon(lng, lat, polygon) for polygon in coordinates)
    return False


def feature_borough(feature: dict[str, Any]) -> str | None:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    for key, value in props.items():
        normalized_key = re.sub(r"[^a-z]", "", str(key).lower())
        if normalized_key in {"boroname", "borough", "boroughname"}:
            borough = canonical_borough(value)
            if borough in BOROUGHS:
                return borough
    return None


def load_boundaries(path: Path) -> list[tuple[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise RuntimeError("Borough boundary GeoJSON has no features array.")
    boundaries: list[tuple[str, dict[str, Any]]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        borough = feature_borough(feature)
        geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
        if borough and geometry:
            boundaries.append((borough, geometry))
    if {borough for borough, _ in boundaries} != set(BOROUGHS):
        raise RuntimeError("Borough boundary GeoJSON does not contain all five canonical boroughs.")
    return boundaries


def borough_for_point(boundaries: list[tuple[str, dict[str, Any]]], lat: float, lng: float) -> str | None:
    matches = [borough for borough, geometry in boundaries if geometry_contains(geometry, lng, lat)]
    return matches[0] if len(matches) == 1 else None


def load_resolver(*, allow_live: bool) -> tuple[NYCLocationGazetteer, NYCLocationResolver]:
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    cache_payload = load_json(GEOSEARCH_CACHE_PATH, {})
    entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
    resolver = NYCLocationResolver(
        gazetteer,
        entries if isinstance(entries, dict) else {},
        allow_live_geosearch=allow_live,
    )
    return gazetteer, resolver


def resolve_one(
    proposal: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
    gazetteer: NYCLocationGazetteer,
    resolver: NYCLocationResolver,
) -> tuple[dict[str, Any], bool]:
    if proposal.get("disposition") != "unresolved":
        return proposal, False

    out = dict(proposal)
    existing_lat = proposal.get("existing_latitude")
    existing_lng = proposal.get("existing_longitude")
    proposed_borough = canonical_borough(proposal.get("proposed_borough"))

    if valid_nyc_lat_lng(existing_lat, existing_lng):
        boundary_borough = borough_for_point(boundaries, float(existing_lat), float(existing_lng))
        if boundary_borough:
            if proposed_borough and proposed_borough != boundary_borough:
                out["reason"] = "Official borough boundary conflicts with earlier same-location borough evidence; retained for manual review."
                out["official_boundary_borough"] = boundary_borough
                return out, False
            out.update(
                {
                    "disposition": "borough_normalized_existing_coordinates",
                    "proposed_borough": boundary_borough,
                    "proposed_latitude": float(existing_lat),
                    "proposed_longitude": float(existing_lng),
                    "pin_eligible": True,
                    "confidence": "high",
                    "reason": "Existing coordinates fall inside one official NYC DCP borough polygon.",
                    "official_boundary_borough": boundary_borough,
                }
            )
            return out, True

    location = str(proposal.get("location") or "")
    if not location or NON_GEOCODABLE_RE.search(location):
        out["reason"] = "No single physical address is available in the source record; no pin fabricated."
        return out, False

    for candidate in raw_location_candidates(location):
        hit = gazetteer.lookup_display(candidate, proposed_borough)
        if isinstance(hit, dict) and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            lat = float(hit["lat"])
            lng = float(hit["lng"])
            boundary_borough = borough_for_point(boundaries, lat, lng)
            if not boundary_borough or (proposed_borough and boundary_borough != proposed_borough):
                continue
            out.update(
                {
                    "disposition": "mapped_from_gazetteer",
                    "proposed_borough": boundary_borough,
                    "proposed_latitude": lat,
                    "proposed_longitude": lng,
                    "pin_eligible": True,
                    "confidence": str(hit.get("confidence") or "medium"),
                    "reason": "Exact candidate matched NYCIF gazetteer and falls inside the matching official borough polygon.",
                    "evidence_source": hit.get("source"),
                    "evidence_label": hit.get("label"),
                    "official_boundary_borough": boundary_borough,
                    "query_used": candidate,
                }
            )
            return out, True

        result = resolver.resolve(display_location=candidate, borough=proposed_borough)
        if not result.resolved or result.lat is None or result.lng is None:
            continue
        boundary_borough = borough_for_point(boundaries, float(result.lat), float(result.lng))
        if not boundary_borough or (proposed_borough and boundary_borough != proposed_borough):
            continue
        out.update(
            {
                "disposition": "mapped_from_live_geosearch"
                if result.tier == "tier_3_nyc_geosearch_live"
                else "mapped_from_gazetteer",
                "proposed_borough": boundary_borough,
                "proposed_latitude": float(result.lat),
                "proposed_longitude": float(result.lng),
                "pin_eligible": True,
                "confidence": result.confidence or "medium",
                "reason": (
                    (result.confidence_reason or "NYC location resolver match.")
                    + " Coordinate falls inside the matching official NYC DCP borough polygon."
                ),
                "evidence_source": result.source,
                "evidence_label": result.label,
                "resolver_tier": result.tier,
                "official_boundary_borough": boundary_borough,
                "query_used": candidate,
            }
        )
        return out, True

    out["reason"] = "No authoritative single-location coordinate match passed borough-boundary validation; no pin fabricated."
    return out, False


def resolve_payload(
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    boundary_path: Path,
    allow_live: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    boundaries = load_boundaries(boundary_path)
    gazetteer, resolver = load_resolver(allow_live=allow_live)
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    before_unresolved = sum(1 for item in proposals if item.get("disposition") == "unresolved")
    resolved: list[dict[str, Any]] = []
    changed = 0
    for proposal in proposals:
        item, did_change = resolve_one(
            proposal,
            boundaries=boundaries,
            gazetteer=gazetteer,
            resolver=resolver,
        )
        resolved.append(item)
        changed += int(did_change)

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in resolved)
    target = int(report.get("target_null_borough_count") or len(resolved))
    boundary_sha = hashlib.sha256(boundary_path.read_bytes()).hexdigest()
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_final",
            "generated_at_utc": utc_now(),
            "accounted_count": len(resolved),
            "location_classified_count": sum(1 for item in resolved if item.get("location_classified") is True),
            "location_classified_pct": round((len(resolved) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in resolved if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1 for item in resolved if valid_nyc_lat_lng(item.get("proposed_latitude"), item.get("proposed_longitude"))
            ),
            "unresolved_count": counts.get("unresolved", 0),
            "zero_silent_null_borough_records": len(resolved) == target,
            "qa_pass": len(resolved) == target and all(item.get("disposition") for item in resolved),
            "official_resolution": {
                "method": "nyc_dcp_boundary_plus_nyc_location_resolver_v1",
                "newly_resolved_count": changed,
                "unresolved_before": before_unresolved,
                "unresolved_after": counts.get("unresolved", 0),
                "allow_live_geosearch": allow_live,
                "live_geosearch_call_count": int(getattr(resolver, "_live_calls", 0)),
                "borough_boundary_source_url": BOUNDARY_SOURCE_URL,
                "borough_boundary_sha256": boundary_sha,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_final",
            "generated_at_utc": final_report["generated_at_utc"],
            "proposals": resolved,
            "official_resolution": final_report["official_resolution"],
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
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--allow-live-geosearch", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    final_report, final_payload = resolve_payload(
        report,
        payload,
        boundary_path=args.borough_boundaries,
        allow_live=args.allow_live_geosearch,
    )
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
