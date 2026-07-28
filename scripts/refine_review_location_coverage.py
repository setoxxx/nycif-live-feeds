#!/usr/bin/env python3
"""Refine unresolved review-location proposals from exact same-snapshot evidence.

This pass is deliberately conservative. It reuses a borough or coordinate only
when the same normalized location appears elsewhere in the same review snapshot,
the borough evidence is unique, and coordinate evidence forms a tight cluster.
It never writes feeds, location_cache.json, WordPress, or public artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.audit_review_location_coverage import (
        BOROUGHS,
        REVIEW_MANIFEST,
        REVIEW_PAGES,
        canonical_borough,
        event_coords,
        load_review_events,
    )
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover
    from audit_review_location_coverage import (
        BOROUGHS,
        REVIEW_MANIFEST,
        REVIEW_PAGES,
        canonical_borough,
        event_coords,
        load_review_events,
    )
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from schema_v1_common import utc_now

ROOT = Path(__file__).resolve().parents[1]
MAX_CLUSTER_DIAMETER_METRES = 250.0
MAX_EXISTING_COORD_DISTANCE_METRES = 500.0


def normalize_location(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def location_candidates(value: Any) -> list[str]:
    text = str(value or "")
    raw_parts = [part.strip() for part in text.split("|") if part.strip()]
    expanded: list[str] = []
    for part in raw_parts:
        expanded.append(part)
        match = re.search(r"\b(?:in|at)\s+(.+)$", part, flags=re.IGNORECASE)
        if match:
            expanded.append(match.group(1).strip())
        if "(" in part and ")" in part:
            inner = re.findall(r"\((?:in\s+)?([^()]+)\)", part, flags=re.IGNORECASE)
            expanded.extend(item.strip() for item in inner if item.strip())
    seen: set[str] = set()
    out: list[str] = []
    for part in expanded:
        key = normalize_location(part)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return sorted(out, key=len, reverse=True)


def review_event_location(event: dict[str, Any]) -> str:
    values = [event.get("location"), event.get("address"), event.get("neighborhood"), event.get("display_location")]
    return " | ".join(str(value).strip() for value in values if str(value or "").strip())


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


def medoid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    unique = sorted(set((round(lat, 7), round(lng, 7)) for lat, lng in points))
    best = unique[0]
    best_total = float("inf")
    for candidate in unique:
        total = sum(haversine_m(candidate[0], candidate[1], other[0], other[1]) for other in unique)
        if total < best_total:
            best = candidate
            best_total = total
    diameter = 0.0
    for index, point in enumerate(unique):
        for other in unique[index + 1 :]:
            diameter = max(diameter, haversine_m(point[0], point[1], other[0], other[1]))
    return best[0], best[1], diameter


def add_evidence(
    index: dict[str, list[dict[str, Any]]],
    *,
    location: Any,
    borough: Any,
    lat: Any,
    lng: Any,
    source: str,
) -> None:
    canonical = canonical_borough(borough)
    if canonical not in BOROUGHS:
        return
    lat_value = float(lat) if valid_nyc_lat_lng(lat, lng) else None
    lng_value = float(lng) if valid_nyc_lat_lng(lat, lng) else None
    for key in location_candidates(location):
        index[key].append(
            {
                "borough": canonical,
                "lat": lat_value,
                "lng": lng_value,
                "source": source,
            }
        )


def build_evidence_index(
    review_events: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in review_events:
        borough = canonical_borough(event.get("borough"))
        if not borough:
            continue
        lat, lng = event_coords(event)
        add_evidence(
            index,
            location=review_event_location(event),
            borough=borough,
            lat=lat,
            lng=lng,
            source="review_record_with_canonical_borough",
        )
    for proposal in proposals:
        borough = proposal.get("proposed_borough")
        lat = proposal.get("proposed_latitude")
        lng = proposal.get("proposed_longitude")
        if not borough:
            continue
        add_evidence(
            index,
            location=proposal.get("location"),
            borough=borough,
            lat=lat,
            lng=lng,
            source=str(proposal.get("disposition") or "resolved_proposal"),
        )
    return index


def unique_borough(entries: list[dict[str, Any]]) -> str | None:
    boroughs = {str(entry.get("borough")) for entry in entries if entry.get("borough")}
    return next(iter(boroughs)) if len(boroughs) == 1 else None


def refine_one(
    proposal: dict[str, Any],
    evidence_index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    if proposal.get("disposition") != "unresolved":
        return proposal, False

    candidates = location_candidates(proposal.get("location"))
    existing_lat = proposal.get("existing_latitude")
    existing_lng = proposal.get("existing_longitude")

    for key in candidates:
        entries = evidence_index.get(key) or []
        borough = unique_borough(entries)
        if not borough:
            continue
        points = [
            (float(entry["lat"]), float(entry["lng"]))
            for entry in entries
            if valid_nyc_lat_lng(entry.get("lat"), entry.get("lng"))
        ]

        if valid_nyc_lat_lng(existing_lat, existing_lng):
            close_points = [
                point
                for point in points
                if haversine_m(float(existing_lat), float(existing_lng), point[0], point[1])
                <= MAX_EXISTING_COORD_DISTANCE_METRES
            ]
            if close_points:
                out = dict(proposal)
                out.update(
                    {
                        "disposition": "borough_normalized_existing_coordinates",
                        "proposed_borough": borough,
                        "proposed_latitude": float(existing_lat),
                        "proposed_longitude": float(existing_lng),
                        "pin_eligible": True,
                        "confidence": "high",
                        "reason": "Exact same-location evidence has one borough and agrees with existing coordinates.",
                        "refinement_key": key,
                        "refinement_evidence_count": len(entries),
                    }
                )
                return out, True
            out = dict(proposal)
            out["proposed_borough"] = borough
            out["reason"] = "Exact same-location evidence identifies the borough, but existing coordinates do not agree closely enough."
            out["refinement_key"] = key
            out["refinement_evidence_count"] = len(entries)
            return out, False

        if not points:
            out = dict(proposal)
            out["proposed_borough"] = borough
            out["reason"] = "Exact same-location evidence identifies the borough, but no coordinate evidence is available."
            out["refinement_key"] = key
            out["refinement_evidence_count"] = len(entries)
            return out, False

        lat, lng, diameter = medoid(points)
        if diameter > MAX_CLUSTER_DIAMETER_METRES:
            out = dict(proposal)
            out["proposed_borough"] = borough
            out["reason"] = "Exact same-location evidence identifies the borough, but coordinate evidence is too dispersed for a safe pin."
            out["refinement_key"] = key
            out["refinement_evidence_count"] = len(entries)
            out["refinement_cluster_diameter_m"] = round(diameter, 1)
            return out, False

        out = dict(proposal)
        out.update(
            {
                "disposition": "mapped_from_internal_location_evidence",
                "proposed_borough": borough,
                "proposed_latitude": lat,
                "proposed_longitude": lng,
                "pin_eligible": True,
                "confidence": "high" if diameter <= 50.0 else "medium",
                "reason": "Exact same-location records in the same snapshot have one borough and a tight coordinate cluster.",
                "refinement_key": key,
                "refinement_evidence_count": len(entries),
                "refinement_cluster_diameter_m": round(diameter, 1),
            }
        )
        return out, True

    return proposal, False


def refine_payload(
    base_report: dict[str, Any],
    base_payload: dict[str, Any],
    review_events: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in base_payload.get("proposals") or [] if isinstance(item, dict)]
    evidence_index = build_evidence_index(review_events, proposals)
    refined: list[dict[str, Any]] = []
    changed = 0
    for proposal in proposals:
        item, did_change = refine_one(proposal, evidence_index)
        refined.append(item)
        changed += int(did_change)

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in refined)
    target = int(base_report.get("target_null_borough_count") or len(refined))
    report = dict(base_report)
    report.update(
        {
            "artifact_type": "review_location_coverage_audit_refined",
            "generated_at_utc": utc_now(),
            "accounted_count": len(refined),
            "location_classified_count": sum(1 for item in refined if item.get("location_classified") is True),
            "location_classified_pct": round((len(refined) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in refined if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1
                for item in refined
                if valid_nyc_lat_lng(item.get("proposed_latitude"), item.get("proposed_longitude"))
            ),
            "unresolved_count": counts.get("unresolved", 0),
            "zero_silent_null_borough_records": len(refined) == target,
            "qa_pass": len(refined) == target and all(item.get("disposition") for item in refined),
            "refinement": {
                "method": "exact_same_snapshot_location_evidence_v1",
                "newly_resolved_count": changed,
                "evidence_key_count": len(evidence_index),
                "max_coordinate_cluster_diameter_m": MAX_CLUSTER_DIAMETER_METRES,
                "max_existing_coordinate_distance_m": MAX_EXISTING_COORD_DISTANCE_METRES,
            },
        }
    )
    payload = dict(base_payload)
    payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_refined",
            "generated_at_utc": report["generated_at_utc"],
            "proposals": refined,
            "refinement": report["refinement"],
        }
    )
    return report, payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--base-proposals", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REVIEW_MANIFEST)
    parser.add_argument("--pages-dir", type=Path, default=REVIEW_PAGES)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()

    base_report = json.loads(args.base_report.read_text(encoding="utf-8"))
    base_payload = json.loads(args.base_proposals.read_text(encoding="utf-8"))
    _manifest, review_events = load_review_events(args.manifest, args.pages_dir)
    report, payload = refine_payload(base_report, base_payload, review_events)
    write_json(args.report, report)
    write_json(args.proposals, payload)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
