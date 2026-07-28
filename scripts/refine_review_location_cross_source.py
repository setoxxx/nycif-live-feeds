#!/usr/bin/env python3
"""Refine unresolved review locations from same-snapshot approved event evidence.

A proposal is resolved only when:

- event title and event date match exactly after normalization;
- the target and evidence locations share distinctive tokens;
- the best evidence agrees on one canonical borough; and
- all winning evidence coordinates form a tight cluster.

After title/date matches, exact normalized locations may propagate those resolved
coordinates to recurring records on other dates. The script writes proposal-only
audit artifacts and never edits discovery feeds, caches, WordPress, or public UI.
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
        ROOT,
        canonical_borough,
        event_coords,
        event_location_text,
        load_review_events,
    )
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover
    from audit_review_location_coverage import (
        ROOT,
        canonical_borough,
        event_coords,
        event_location_text,
        load_review_events,
    )
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from schema_v1_common import utc_now

APPROVED_MANIFEST = ROOT / "data" / "schema-v1-discovery" / "approved" / "manifest.json"
APPROVED_PAGES = APPROVED_MANIFEST.parent / "pages"
DEFAULT_INPUT_REPORT = ROOT / "data" / "reports" / "review_location_coverage_audit.json"
DEFAULT_INPUT_PROPOSALS = ROOT / "data" / "staging" / "review_location_resolution_proposals.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "review_location_cross_source_audit.json"
DEFAULT_PROPOSALS = ROOT / "data" / "staging" / "review_location_cross_source_proposals.json"

MAX_CLUSTER_DIAMETER_M = 250.0

GENERIC_LOCATION_TOKENS = {
    "at",
    "avenue",
    "ave",
    "boulevard",
    "bronx",
    "brooklyn",
    "center",
    "centre",
    "ctr",
    "field",
    "gym",
    "gymnasium",
    "island",
    "lot",
    "manhattan",
    "multi",
    "new",
    "ny",
    "park",
    "parking",
    "playground",
    "pool",
    "queens",
    "recreation",
    "road",
    "room",
    "staten",
    "street",
    "the",
    "under",
    "use",
    "usa",
    "york",
}


def normalized_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\bst\.?\s+(?=[a-z])", "saint ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def title_key(value: Any) -> str:
    return normalized_text(value)


def semantic_location_tokens(value: Any) -> set[str]:
    tokens = set(normalized_text(value).split())
    return {
        token
        for token in tokens
        if token not in GENERIC_LOCATION_TOKENS and (len(token) >= 3 or token.isdigit())
    }


def exact_location_key(value: Any) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").split("|"):
        key = normalized_text(raw)
        if key and key not in seen:
            seen.add(key)
            parts.append(key)
    return " | ".join(parts)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


def cluster_diameter_m(rows: list[dict[str, Any]]) -> float:
    diameter = 0.0
    for index, first in enumerate(rows):
        for second in rows[index + 1 :]:
            diameter = max(
                diameter,
                haversine_m(
                    float(first["latitude"]),
                    float(first["longitude"]),
                    float(second["latitude"]),
                    float(second["longitude"]),
                ),
            )
    return diameter


def event_date(event: dict[str, Any]) -> str | None:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return nycif.get("event_date") or str(event.get("start_date_time") or "")[:10] or None


def evidence_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    lat, lng = event_coords(event)
    borough = canonical_borough(event.get("borough"))
    if not borough or not valid_nyc_lat_lng(lat, lng):
        return None
    return {
        "canonical_id": event.get("id"),
        "title": event.get("title"),
        "date": event_date(event),
        "location": event_location_text(event),
        "borough": borough,
        "latitude": float(lat),
        "longitude": float(lng),
        "source_kind": "approved_discovery_event",
    }


def evidence_from_proposal(proposal: dict[str, Any]) -> dict[str, Any] | None:
    if proposal.get("disposition") == "unresolved":
        return None
    borough = canonical_borough(proposal.get("proposed_borough"))
    lat = proposal.get("proposed_latitude")
    lng = proposal.get("proposed_longitude")
    if not borough or not valid_nyc_lat_lng(lat, lng):
        return None
    return {
        "canonical_id": proposal.get("canonical_id"),
        "title": proposal.get("title"),
        "date": proposal.get("date"),
        "location": proposal.get("location"),
        "borough": borough,
        "latitude": float(lat),
        "longitude": float(lng),
        "source_kind": "resolved_review_proposal",
    }


def choose_representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) == 1:
        return rows[0]
    center_lat = sum(float(row["latitude"]) for row in rows) / len(rows)
    center_lng = sum(float(row["longitude"]) for row in rows) / len(rows)
    return min(
        rows,
        key=lambda row: haversine_m(
            center_lat,
            center_lng,
            float(row["latitude"]),
            float(row["longitude"]),
        ),
    )


def safe_cluster(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    if not rows:
        return None, 0.0
    boroughs = {row["borough"] for row in rows}
    if len(boroughs) != 1:
        return None, 0.0
    diameter = cluster_diameter_m(rows)
    if diameter > MAX_CLUSTER_DIAMETER_M:
        return None, diameter
    return choose_representative(rows), diameter


def build_evidence(proposals: list[dict[str, Any]], approved_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for event in approved_events:
        row = evidence_from_event(event)
        if row:
            evidence.append(row)
    for proposal in proposals:
        row = evidence_from_proposal(proposal)
        if row:
            evidence.append(row)
    return evidence


def resolve_title_date(
    proposal: dict[str, Any],
    evidence_index: dict[tuple[str, str | None], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    target_tokens = semantic_location_tokens(proposal.get("location"))
    if not target_tokens:
        return None
    candidates = evidence_index.get((title_key(proposal.get("title")), proposal.get("date")), [])
    scored: list[tuple[int, float, dict[str, Any]]] = []
    for row in candidates:
        evidence_tokens = semantic_location_tokens(row.get("location"))
        overlap = target_tokens.intersection(evidence_tokens)
        if not overlap:
            continue
        score = len(overlap)
        coverage = score / max(1, len(target_tokens))
        scored.append((score, coverage, row))
    if not scored:
        return None
    best_score = max(score for score, _, _ in scored)
    best_coverage = max(coverage for score, coverage, _ in scored if score == best_score)
    winners = [
        row
        for score, coverage, row in scored
        if score == best_score and abs(coverage - best_coverage) < 1e-12
    ]
    representative, diameter = safe_cluster(winners)
    if representative is None:
        return None
    return {
        "representative": representative,
        "evidence": winners,
        "overlap_score": best_score,
        "target_token_coverage": round(best_coverage, 4),
        "cluster_diameter_m": round(diameter, 1),
    }


def resolve_exact_location(
    proposal: dict[str, Any],
    location_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    key = exact_location_key(proposal.get("location"))
    if not key:
        return None
    candidates = location_index.get(key, [])
    representative, diameter = safe_cluster(candidates)
    if representative is None:
        return None
    return {
        "representative": representative,
        "evidence": candidates,
        "cluster_diameter_m": round(diameter, 1),
    }


def apply_resolution(
    proposal: dict[str, Any],
    match: dict[str, Any],
    *,
    disposition: str,
    reason: str,
) -> dict[str, Any]:
    representative = match["representative"]
    out = dict(proposal)
    out.update(
        {
            "disposition": disposition,
            "proposed_borough": representative["borough"],
            "proposed_latitude": representative["latitude"],
            "proposed_longitude": representative["longitude"],
            "pin_eligible": True,
            "confidence": "high" if match.get("cluster_diameter_m", 0.0) <= 35.0 else "medium",
            "reason": reason,
            "cross_source_evidence_ids": [
                row.get("canonical_id") for row in match["evidence"][:20] if row.get("canonical_id")
            ],
            "cross_source_cluster_diameter_m": match.get("cluster_diameter_m", 0.0),
        }
    )
    if "overlap_score" in match:
        out["cross_source_location_overlap_score"] = match["overlap_score"]
        out["cross_source_target_token_coverage"] = match["target_token_coverage"]
    return out


def refine_payload(
    report: dict[str, Any],
    payload: dict[str, Any],
    approved_events: list[dict[str, Any]],
    *,
    approved_generated_at_utc: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    before = sum(1 for item in proposals if item.get("disposition") == "unresolved")
    title_date_resolved = 0
    exact_location_resolved = 0

    for _ in range(4):
        changed = 0
        evidence = build_evidence(proposals, approved_events)
        title_date_index: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
        for row in evidence:
            key = (title_key(row.get("title")), row.get("date"))
            if key[0] and key[1]:
                title_date_index[key].append(row)

        updated: list[dict[str, Any]] = []
        for proposal in proposals:
            if proposal.get("disposition") != "unresolved":
                updated.append(proposal)
                continue
            match = resolve_title_date(proposal, title_date_index)
            if not match:
                updated.append(proposal)
                continue
            updated.append(
                apply_resolution(
                    proposal,
                    match,
                    disposition="mapped_from_cross_source_event_evidence",
                    reason=(
                        "Exact normalized title and date match official same-snapshot evidence; "
                        "distinctive location tokens agree and all winning coordinates form one borough cluster."
                    ),
                )
            )
            title_date_resolved += 1
            changed += 1
        proposals = updated

        evidence = build_evidence(proposals, approved_events)
        location_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in evidence:
            key = exact_location_key(row.get("location"))
            if key:
                location_index[key].append(row)

        updated = []
        for proposal in proposals:
            if proposal.get("disposition") != "unresolved":
                updated.append(proposal)
                continue
            match = resolve_exact_location(proposal, location_index)
            if not match:
                updated.append(proposal)
                continue
            updated.append(
                apply_resolution(
                    proposal,
                    match,
                    disposition="mapped_from_cross_source_location_evidence",
                    reason=(
                        "Exact normalized location matches resolved same-snapshot evidence with one borough "
                        "and a tight coordinate cluster."
                    ),
                )
            )
            exact_location_resolved += 1
            changed += 1
        proposals = updated
        if changed == 0:
            break

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in proposals)
    target = int(report.get("target_null_borough_count") or len(proposals))
    unresolved_after = counts.get("unresolved", 0)
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_cross_source",
            "generated_at_utc": utc_now(),
            "accounted_count": len(proposals),
            "location_classified_count": sum(1 for item in proposals if item.get("location_classified") is True),
            "location_classified_pct": round((len(proposals) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in proposals if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1
                for item in proposals
                if valid_nyc_lat_lng(item.get("proposed_latitude"), item.get("proposed_longitude"))
            ),
            "unresolved_count": unresolved_after,
            "zero_silent_null_borough_records": len(proposals) == target,
            "qa_pass": len(proposals) == target and all(item.get("disposition") for item in proposals),
            "cross_source_refinement": {
                "method": "exact_title_date_plus_distinctive_location_cluster_v1",
                "approved_manifest_generated_at_utc": approved_generated_at_utc,
                "approved_evidence_event_count": sum(
                    1 for event in approved_events if evidence_from_event(event) is not None
                ),
                "max_cluster_diameter_m": MAX_CLUSTER_DIAMETER_M,
                "unresolved_before": before,
                "unresolved_after": unresolved_after,
                "newly_resolved_count": before - unresolved_after,
                "title_date_resolved_count": title_date_resolved,
                "exact_location_propagated_count": exact_location_resolved,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_cross_source",
            "generated_at_utc": final_report["generated_at_utc"],
            "target_count": target,
            "proposals": proposals,
        }
    )
    return final_report, final_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-report", type=Path, default=DEFAULT_INPUT_REPORT)
    parser.add_argument("--input-proposals", type=Path, default=DEFAULT_INPUT_PROPOSALS)
    parser.add_argument("--approved-manifest", type=Path, default=APPROVED_MANIFEST)
    parser.add_argument("--approved-pages", type=Path, default=APPROVED_PAGES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    approved_manifest, approved_events = load_review_events(args.approved_manifest, args.approved_pages)
    source_generated = report.get("source_generated_at_utc")
    approved_generated = approved_manifest.get("generated_at_utc")
    if source_generated and approved_generated and source_generated != approved_generated:
        raise RuntimeError(
            "Approved and review artifacts are not from the same snapshot: "
            f"review={source_generated}, approved={approved_generated}"
        )
    final_report, final_payload = refine_payload(
        report,
        payload,
        approved_events,
        approved_generated_at_utc=approved_generated,
    )
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
