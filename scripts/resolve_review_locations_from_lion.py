#!/usr/bin/env python3
"""Resolve review street segments from official NYC DCP LION intersection nodes.

For unresolved records whose source states an on-street and two cross streets,
this audit-only resolver:

1. queries the current NYC DCP LION line service for the relevant street names;
2. identifies shared NodeID intersections for the on-street and each cross street;
3. retrieves those official node points in WGS84;
4. selects the shortest valid pair of distinct endpoint nodes; and
5. accepts the midpoint only when both endpoints and midpoint fall inside the
   declared official DCP borough polygon.

The script writes proposals and evidence only. It never writes a location cache,
discovery feed, WordPress page, or public map surface.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.audit_review_location_coverage import canonical_borough
    from scripts.resolve_remaining_review_locations import borough_for_point, load_boundaries
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover
    from audit_review_location_coverage import canonical_borough
    from resolve_remaining_review_locations import borough_for_point, load_boundaries
    from schema_v1_common import utc_now

LION_LINE_URL = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/LION/FeatureServer/0/query"
LION_NODE_URL = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/LION_Node/FeatureServer/0/query"
LION_LAYER_URL = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/LION/FeatureServer/0"
LION_NODE_LAYER_URL = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/LION_Node/FeatureServer/0"

HTTP_TIMEOUT_SEC = 25
REQUEST_DELAY_SEC = 0.05
PAGE_SIZE = 2000
MAX_PAIR_DISTANCE_M = 5000.0
MIN_PAIR_DISTANCE_M = 10.0

BOROUGH_CODES = {
    "Manhattan": 1,
    "Bronx": 2,
    "Brooklyn": 3,
    "Queens": 4,
    "Staten Island": 5,
}

BETWEEN_RE = re.compile(
    r"^(?P<main>.+?)\s+between\s+(?P<cross1>.+?)\s+and\s+(?P<cross2>.+)$",
    flags=re.IGNORECASE,
)
BOROUGH_SUFFIX_RE = re.compile(
    r"\s+(?P<borough>Manhattan|Brooklyn|Queens|Bronx|Staten Island)\s*$",
    flags=re.IGNORECASE,
)

WORD_TO_NUMBER = {
    "FIRST": "1",
    "SECOND": "2",
    "THIRD": "3",
    "FOURTH": "4",
    "FIFTH": "5",
    "SIXTH": "6",
    "SEVENTH": "7",
    "EIGHTH": "8",
    "NINTH": "9",
    "TENTH": "10",
    "ELEVENTH": "11",
    "TWELFTH": "12",
}
NUMBER_TO_WORD = {value: key for key, value in WORD_TO_NUMBER.items()}

DIRECTION_CANON = {
    "EAST": "E",
    "E": "E",
    "WEST": "W",
    "W": "W",
    "NORTH": "N",
    "N": "N",
    "SOUTH": "S",
    "S": "S",
}
SUFFIX_CANON = {
    "STREET": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "ROAD": "RD",
    "RD": "RD",
    "PLACE": "PL",
    "PL": "PL",
    "PARKWAY": "PKWY",
    "PKWY": "PKWY",
    "DRIVE": "DR",
    "DR": "DR",
    "LANE": "LN",
    "LN": "LN",
    "TERRACE": "TER",
    "TER": "TER",
    "COURT": "CT",
    "CT": "CT",
    "SQUARE": "SQ",
    "SQ": "SQ",
}


def normalized_words(value: Any) -> list[str]:
    text = str(value or "").upper()
    text = re.sub(r"\b(\d+)(?:ST|ND|RD|TH)\b", r"\1", text)
    words = re.findall(r"[A-Z0-9]+", text)
    out: list[str] = []
    for word in words:
        word = WORD_TO_NUMBER.get(word, word)
        word = DIRECTION_CANON.get(word, word)
        word = SUFFIX_CANON.get(word, word)
        out.append(word)
    return out


def street_key(value: Any) -> str:
    return " ".join(normalized_words(value))


def street_variants(value: Any) -> set[str]:
    words = normalized_words(value)
    if not words:
        return set()
    variants = {" ".join(words)}

    expanded: list[str] = []
    direction_expand = {"E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH"}
    suffix_expand = {
        "ST": "STREET",
        "AVE": "AVENUE",
        "BLVD": "BOULEVARD",
        "RD": "ROAD",
        "PL": "PLACE",
        "PKWY": "PARKWAY",
        "DR": "DRIVE",
        "LN": "LANE",
        "TER": "TERRACE",
        "CT": "COURT",
        "SQ": "SQUARE",
    }
    for word in words:
        expanded.append(direction_expand.get(word, suffix_expand.get(word, word)))
    variants.add(" ".join(expanded))

    ordinal_words = [NUMBER_TO_WORD.get(word, word) for word in words]
    variants.add(" ".join(ordinal_words))
    ordinal_expanded = [
        direction_expand.get(word, suffix_expand.get(word, NUMBER_TO_WORD.get(word, word)))
        for word in words
    ]
    variants.add(" ".join(ordinal_expanded))

    key = " ".join(words)
    if key in {"6 AVE", "6 AVENUE", "SIXTH AVE", "SIXTH AVENUE"}:
        variants.update({"6 AVE", "6 AVENUE", "SIXTH AVE", "SIXTH AVENUE", "AVENUE OF THE AMERICAS"})
    if key in {"7 AVE", "7 AVENUE", "SEVENTH AVE", "SEVENTH AVENUE"}:
        variants.update({"7 AVE", "7 AVENUE", "SEVENTH AVE", "SEVENTH AVENUE"})
    if key in {"3 AVE", "3 AVENUE", "THIRD AVE", "THIRD AVENUE"}:
        variants.update({"3 AVE", "3 AVENUE", "THIRD AVE", "THIRD AVENUE"})
    if key in {"2 AVE", "2 AVENUE", "SECOND AVE", "SECOND AVENUE"}:
        variants.update({"2 AVE", "2 AVENUE", "SECOND AVE", "SECOND AVENUE"})
    return {re.sub(r"\s+", " ", variant.strip().upper()) for variant in variants if variant.strip()}


def parse_segment_location(value: Any) -> tuple[str, str, str, str | None] | None:
    first = str(value or "").split("|")[0].strip()
    if not first:
        return None
    suffix = BOROUGH_SUFFIX_RE.search(first)
    borough = canonical_borough(suffix.group("borough")) if suffix else None
    if suffix:
        first = first[: suffix.start()].strip()
    match = BETWEEN_RE.match(first)
    if not match:
        return None
    main = match.group("main").strip(" ,.")
    cross1 = match.group("cross1").strip(" ,.")
    cross2 = match.group("cross2").strip(" ,.")
    if not main or not cross1 or not cross2:
        return None
    return main, cross1, cross2, borough


def arcgis_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "nycif-review-location-lion-audit/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SEC) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LION request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"LION response is not an object for {url}")
    if payload.get("error"):
        raise RuntimeError(f"LION service error for {url}: {payload['error']}")
    time.sleep(REQUEST_DELAY_SEC)
    return payload


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def batched(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_lion_lines(borough: str, requested_streets: set[str]) -> list[dict[str, Any]]:
    code = BOROUGH_CODES[borough]
    all_variants = sorted({variant for street in requested_streets for variant in street_variants(street)})
    rows: dict[int, dict[str, Any]] = {}
    for variant_batch in batched(all_variants, 60):
        values = ",".join(sql_quote(value) for value in variant_batch)
        street_clause = f"(Street IN ({values}) OR SAFStreetName IN ({values}))"
        where = f"(LBoro={code} OR RBoro={code}) AND {street_clause}"
        offset = 0
        while True:
            payload = arcgis_get(
                LION_LINE_URL,
                {
                    "where": where,
                    "outFields": "OBJECTID,Street,SAFStreetName,NodeIDFrom,NodeIDTo,LBoro,RBoro",
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID",
                    "resultOffset": offset,
                    "resultRecordCount": PAGE_SIZE,
                    "f": "json",
                },
            )
            features = payload.get("features") or []
            if not isinstance(features, list):
                raise RuntimeError("LION line query returned no feature list.")
            for feature in features:
                attrs = feature.get("attributes") if isinstance(feature, dict) else None
                if not isinstance(attrs, dict):
                    continue
                object_id = attrs.get("OBJECTID")
                if object_id is not None:
                    rows[int(object_id)] = attrs
            if len(features) < PAGE_SIZE and not payload.get("exceededTransferLimit"):
                break
            offset += len(features)
            if not features:
                break
    return list(rows.values())


def node_street_index(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        names = {
            street_key(row.get("Street")),
            street_key(row.get("SAFStreetName")),
        }
        names.discard("")
        for field in ("NodeIDFrom", "NodeIDTo"):
            node_id = str(row.get(field) or "").strip()
            if node_id:
                index[node_id].update(names)
    return index


def matching_nodes(index: dict[str, set[str]], street1: str, street2: str) -> set[str]:
    key1 = street_key(street1)
    key2 = street_key(street2)
    return {
        node_id
        for node_id, names in index.items()
        if key1 in names and key2 in names
    }


def fetch_node_points(node_ids: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    numeric_ids = sorted({str(int(node_id)) for node_id in node_ids if str(node_id).strip().isdigit()})
    for chunk in batched(numeric_ids, 500):
        where = "NODEID IN (" + ",".join(chunk) + ")"
        payload = arcgis_get(
            LION_NODE_URL,
            {
                "where": where,
                "outFields": "NODEID,VIntersect",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "json",
            },
        )
        features = payload.get("features") or []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
            node_id = str(attrs.get("NODEID") or "").strip()
            x = geometry.get("x")
            y = geometry.get("y")
            try:
                lng = float(x)
                lat = float(y)
            except (TypeError, ValueError):
                continue
            if node_id and -75.0 <= lng <= -73.0 and 40.0 <= lat <= 41.0:
                result[node_id] = {
                    "node_id": node_id,
                    "latitude": lat,
                    "longitude": lng,
                    "v_intersect": attrs.get("VIntersect"),
                }
    return result


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


def choose_endpoint_pair(
    first_nodes: set[str],
    second_nodes: set[str],
    points: dict[str, dict[str, Any]],
    *,
    borough: str,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for first_id in first_nodes:
        first = points.get(first_id)
        if not first:
            continue
        if borough_for_point(boundaries, first["latitude"], first["longitude"]) != borough:
            continue
        for second_id in second_nodes:
            if second_id == first_id:
                continue
            second = points.get(second_id)
            if not second:
                continue
            if borough_for_point(boundaries, second["latitude"], second["longitude"]) != borough:
                continue
            distance = haversine_m(
                first["latitude"],
                first["longitude"],
                second["latitude"],
                second["longitude"],
            )
            if not (MIN_PAIR_DISTANCE_M <= distance <= MAX_PAIR_DISTANCE_M):
                continue
            midpoint_lat = round((first["latitude"] + second["latitude"]) / 2.0, 7)
            midpoint_lng = round((first["longitude"] + second["longitude"]) / 2.0, 7)
            if borough_for_point(boundaries, midpoint_lat, midpoint_lng) != borough:
                continue
            candidates.append(
                {
                    "first": first,
                    "second": second,
                    "distance_m": distance,
                    "midpoint_latitude": midpoint_lat,
                    "midpoint_longitude": midpoint_lng,
                }
            )
    if not candidates:
        return None
    return min(candidates, key=lambda item: item["distance_m"])


def resolve_payload(
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    before = sum(1 for item in proposals if item.get("disposition") == "unresolved")

    parsed_by_borough: dict[str, list[tuple[int, tuple[str, str, str, str | None]]]] = defaultdict(list)
    streets_by_borough: dict[str, set[str]] = defaultdict(set)
    for index, proposal in enumerate(proposals):
        if proposal.get("disposition") != "unresolved":
            continue
        parsed = parse_segment_location(proposal.get("location"))
        if not parsed:
            continue
        main, cross1, cross2, suffix_borough = parsed
        borough = canonical_borough(proposal.get("proposed_borough")) or suffix_borough
        if borough not in BOROUGH_CODES:
            continue
        parsed_by_borough[borough].append((index, parsed))
        streets_by_borough[borough].update({main, cross1, cross2})

    street_match_counts: dict[str, dict[str, int]] = {}
    endpoint_diagnostics: list[dict[str, Any]] = []
    changed = 0

    for borough, records in parsed_by_borough.items():
        rows = fetch_lion_lines(borough, streets_by_borough[borough])
        index = node_street_index(rows)
        street_match_counts[borough] = {
            street: sum(1 for names in index.values() if street_key(street) in names)
            for street in sorted(streets_by_borough[borough])
        }

        candidate_node_ids: set[str] = set()
        record_nodes: dict[int, tuple[set[str], set[str]]] = {}
        for proposal_index, parsed in records:
            main, cross1, cross2, _ = parsed
            first_nodes = matching_nodes(index, main, cross1)
            second_nodes = matching_nodes(index, main, cross2)
            record_nodes[proposal_index] = (first_nodes, second_nodes)
            candidate_node_ids.update(first_nodes)
            candidate_node_ids.update(second_nodes)

        points = fetch_node_points(candidate_node_ids)
        for proposal_index, parsed in records:
            main, cross1, cross2, _ = parsed
            first_nodes, second_nodes = record_nodes[proposal_index]
            pair = choose_endpoint_pair(
                first_nodes,
                second_nodes,
                points,
                borough=borough,
                boundaries=boundaries,
            )
            diagnostic = {
                "canonical_id": proposals[proposal_index].get("canonical_id"),
                "borough": borough,
                "main_street": main,
                "cross_street_1": cross1,
                "cross_street_2": cross2,
                "first_node_candidates": sorted(first_nodes),
                "second_node_candidates": sorted(second_nodes),
                "resolved": pair is not None,
            }
            if pair is None:
                endpoint_diagnostics.append(diagnostic)
                continue
            first = pair["first"]
            second = pair["second"]
            out = dict(proposals[proposal_index])
            out.update(
                {
                    "disposition": "mapped_from_nyc_lion_nodes",
                    "proposed_borough": borough,
                    "proposed_latitude": pair["midpoint_latitude"],
                    "proposed_longitude": pair["midpoint_longitude"],
                    "pin_eligible": True,
                    "confidence": "high",
                    "reason": (
                        "Official NYC DCP LION nodes identify both stated intersections on the named street; "
                        "both endpoints and their midpoint fall inside the declared borough polygon."
                    ),
                    "lion_main_street": main,
                    "lion_cross_streets": [cross1, cross2],
                    "lion_endpoint_node_ids": [first["node_id"], second["node_id"]],
                    "lion_endpoint_labels": [first.get("v_intersect"), second.get("v_intersect")],
                    "lion_endpoint_coordinates": [
                        [first["latitude"], first["longitude"]],
                        [second["latitude"], second["longitude"]],
                    ],
                    "lion_segment_length_m": round(pair["distance_m"], 1),
                    "evidence_source": "nyc_dcp_lion_26b_feature_services",
                    "official_boundary_borough": borough,
                }
            )
            proposals[proposal_index] = out
            changed += 1
            diagnostic.update(
                {
                    "resolved": True,
                    "selected_node_ids": [first["node_id"], second["node_id"]],
                    "segment_length_m": round(pair["distance_m"], 1),
                }
            )
            endpoint_diagnostics.append(diagnostic)

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in proposals)
    target = int(report.get("target_null_borough_count") or len(proposals))
    unresolved_after = counts.get("unresolved", 0)
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_lion",
            "generated_at_utc": utc_now(),
            "accounted_count": len(proposals),
            "location_classified_count": sum(1 for item in proposals if item.get("location_classified") is True),
            "location_classified_pct": round((len(proposals) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in proposals if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1
                for item in proposals
                if item.get("proposed_latitude") is not None and item.get("proposed_longitude") is not None
            ),
            "unresolved_count": unresolved_after,
            "zero_silent_null_borough_records": len(proposals) == target,
            "qa_pass": len(proposals) == target and all(item.get("disposition") for item in proposals),
            "lion_resolution": {
                "method": "nyc_dcp_lion_shared_node_midpoint_v1",
                "line_layer_url": LION_LAYER_URL,
                "node_layer_url": LION_NODE_LAYER_URL,
                "release_context": "Current LION feature services; Open Data catalog identifies current release as 26b.",
                "unresolved_before": before,
                "unresolved_after": unresolved_after,
                "newly_resolved_count": changed,
                "street_match_counts": street_match_counts,
                "endpoint_diagnostics": endpoint_diagnostics,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_lion",
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
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--input-proposals", type=Path, required=True)
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    boundaries = load_boundaries(args.borough_boundaries)
    final_report, final_payload = resolve_payload(report, payload, boundaries=boundaries)
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
