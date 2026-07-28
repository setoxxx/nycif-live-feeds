#!/usr/bin/env python3
"""Classify every null-borough discovery-review record without inventing map pins.

The audit is fail-closed and staging-only. It does not edit discovery feeds,
location_cache.json, WordPress, or any public map artifact. It writes a report
and a proposal file that separate:

- borough-normalized records with existing coordinates;
- newly mapped physical locations supported by gazetteer/geosearch evidence;
- online records;
- citywide or multi-location records; and
- unresolved physical locations with an explicit reason.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.nyc_location_gazetteer import (
        GAZETTEER_PATH,
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
        load_json,
        valid_nyc_lat_lng,
    )
    from scripts.nyc_location_resolver import NYCLocationResolver
    from scripts.schema_v1_common import BOROUGH_MAP, borough_label, utc_now
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from nyc_location_gazetteer import (
        GAZETTEER_PATH,
        GEOSEARCH_CACHE_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
        load_json,
        valid_nyc_lat_lng,
    )
    from nyc_location_resolver import NYCLocationResolver
    from schema_v1_common import BOROUGH_MAP, borough_label, utc_now

ROOT = Path(__file__).resolve().parents[1]
REVIEW_MANIFEST = ROOT / "data" / "schema-v1-discovery" / "review" / "manifest.json"
REVIEW_PAGES = REVIEW_MANIFEST.parent / "pages"
DEFAULT_REPORT = ROOT / "data" / "reports" / "review_location_coverage_audit.json"
DEFAULT_PROPOSALS = ROOT / "data" / "staging" / "review_location_resolution_proposals.json"

BOROUGHS = ("Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island")
GRID_STEP = 0.002  # roughly 170-220 metres in NYC
MAX_NEARBY_METRES = 350.0
AMBIGUITY_MARGIN_METRES = 75.0

ONLINE_RE = re.compile(
    r"\bvirtual\b|\bonline\b|\bwebinar\b|\bzoom\b|\bremote\b|livestream|live stream",
    flags=re.IGNORECASE,
)
CITYWIDE_RE = re.compile(
    r"\bcitywide\b|all five boroughs|across all five boroughs|locations across|"
    r"multiple locations|various locations|participating locations|throughout new york city",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class SpatialEntry:
    lat: float
    lng: float
    borough: str
    label: str | None
    source: str | None


def canonical_borough(value: Any) -> str | None:
    normalized = borough_label(value)
    if normalized in BOROUGHS:
        return normalized
    raw = str(value or "").strip().lower()
    if raw in BOROUGH_MAP:
        return BOROUGH_MAP[raw]
    return None


def event_coords(event: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = event.get("latitude") if event.get("latitude") is not None else event.get("lat")
    lng = event.get("longitude") if event.get("longitude") is not None else event.get("lng")
    if valid_nyc_lat_lng(lat, lng):
        return float(lat), float(lng)
    return None, None


def event_location_text(event: dict[str, Any]) -> str:
    values = [
        event.get("location"),
        event.get("address"),
        event.get("neighborhood"),
        event.get("display_location"),
    ]
    return " | ".join(str(value).strip() for value in values if str(value or "").strip())


def source_identity(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return {
        "dataset": source.get("dataset"),
        "source_event_id": source.get("source_event_id"),
        "source_url": source.get("source_url"),
    }


def load_review_events(
    manifest_path: Path = REVIEW_MANIFEST,
    pages_dir: Path = REVIEW_PAGES,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_json(manifest_path, {})
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Review manifest is not an object: {manifest_path}")
    events: list[dict[str, Any]] = []
    for page_meta in manifest.get("pages") or []:
        if not isinstance(page_meta, dict):
            continue
        page_name = str(page_meta.get("page") or "").strip()
        if not page_name:
            continue
        payload = load_json(pages_dir / page_name, {})
        page_events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(page_events, list):
            raise RuntimeError(f"Review page has no events array: {page_name}")
        events.extend(row for row in page_events if isinstance(row, dict))
    expected = int(manifest.get("total") or 0)
    if len(events) != expected:
        raise RuntimeError(f"Review manifest/page mismatch: expected {expected}, loaded {len(events)}")
    return manifest, events


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


def grid_key(lat: float, lng: float) -> tuple[int, int]:
    return int(math.floor(lat / GRID_STEP)), int(math.floor(lng / GRID_STEP))


def build_spatial_index(gazetteer: NYCLocationGazetteer) -> dict[tuple[int, int], list[SpatialEntry]]:
    index: dict[tuple[int, int], list[SpatialEntry]] = defaultdict(list)
    seen: set[tuple[float, float, str, str | None]] = set()
    for raw in gazetteer.index.values():
        if not isinstance(raw, dict) or not valid_nyc_lat_lng(raw.get("lat"), raw.get("lng")):
            continue
        borough = canonical_borough(raw.get("borough"))
        if not borough:
            continue
        lat = float(raw["lat"])
        lng = float(raw["lng"])
        label = str(raw.get("label") or "").strip() or None
        dedupe_key = (round(lat, 7), round(lng, 7), borough, label)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entry = SpatialEntry(lat, lng, borough, label, str(raw.get("source") or "") or None)
        index[grid_key(lat, lng)].append(entry)
    return index


def nearest_borough(
    spatial_index: dict[tuple[int, int], list[SpatialEntry]],
    lat: float,
    lng: float,
) -> dict[str, Any] | None:
    base_x, base_y = grid_key(lat, lng)
    best_by_borough: dict[str, tuple[float, SpatialEntry]] = {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for entry in spatial_index.get((base_x + dx, base_y + dy), []):
                distance = haversine_m(lat, lng, entry.lat, entry.lng)
                if distance > MAX_NEARBY_METRES:
                    continue
                current = best_by_borough.get(entry.borough)
                if current is None or distance < current[0]:
                    best_by_borough[entry.borough] = (distance, entry)
    ranked = sorted(best_by_borough.values(), key=lambda pair: pair[0])
    if not ranked:
        return None
    best_distance, best_entry = ranked[0]
    if len(ranked) > 1 and ranked[1][0] - best_distance < AMBIGUITY_MARGIN_METRES:
        return {
            "ambiguous": True,
            "reason": "Nearby gazetteer evidence crosses boroughs within the ambiguity margin.",
            "candidates": [
                {"borough": entry.borough, "distance_m": round(distance, 1)}
                for distance, entry in ranked[:3]
            ],
        }
    return {
        "ambiguous": False,
        "borough": best_entry.borough,
        "distance_m": round(best_distance, 1),
        "label": best_entry.label,
        "source": best_entry.source,
        "confidence": "high" if best_distance <= 35 else "medium",
    }


def borough_from_text(text: str) -> str | None:
    found: set[str] = set()
    lower = str(text or "").lower()
    patterns = {
        "Manhattan": (r"\bmanhattan\b", r"\bnew york,? ny\b"),
        "Brooklyn": (r"\bbrooklyn\b",),
        "Queens": (r"\bqueens\b",),
        "Bronx": (r"\bbronx\b",),
        "Staten Island": (r"\bstaten island\b",),
    }
    for borough, borough_patterns in patterns.items():
        if any(re.search(pattern, lower) for pattern in borough_patterns):
            found.add(borough)
    return next(iter(found)) if len(found) == 1 else None


def online_or_citywide(text: str) -> str | None:
    if ONLINE_RE.search(text):
        return "online"
    if CITYWIDE_RE.search(text):
        return "citywide_or_multi_location"
    return None


def base_proposal(event: dict[str, Any]) -> dict[str, Any]:
    lat, lng = event_coords(event)
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return {
        "canonical_id": event.get("id"),
        "title": event.get("title"),
        "date": nycif.get("event_date"),
        "source": source_identity(event),
        "location": event_location_text(event) or None,
        "existing_latitude": lat,
        "existing_longitude": lng,
        "existing_borough": event.get("borough"),
        "public_map_modified": False,
        "promotion_allowed": False,
    }


def resolve_null_borough_event(
    event: dict[str, Any],
    *,
    gazetteer: NYCLocationGazetteer,
    spatial_index: dict[tuple[int, int], list[SpatialEntry]],
    resolver: NYCLocationResolver | None = None,
) -> dict[str, Any]:
    proposal = base_proposal(event)
    location = str(proposal.get("location") or "")
    title = str(event.get("title") or "")
    combined = " | ".join(part for part in (location, title) if part)
    nonphysical = online_or_citywide(combined)
    if nonphysical:
        proposal.update(
            {
                "disposition": nonphysical,
                "location_classified": True,
                "pin_eligible": False,
                "reason": "Explicit non-single-location language in the event record.",
            }
        )
        return proposal

    lat, lng = event_coords(event)
    text_borough = borough_from_text(location)

    if lat is not None and lng is not None:
        if text_borough:
            proposal.update(
                {
                    "disposition": "borough_normalized_existing_coordinates",
                    "location_classified": True,
                    "pin_eligible": True,
                    "proposed_borough": text_borough,
                    "proposed_latitude": lat,
                    "proposed_longitude": lng,
                    "confidence": "high",
                    "reason": "Unique borough name in physical location text; existing coordinates retained.",
                }
            )
            return proposal

        display_hit = gazetteer.lookup_display(location, None) if location else None
        hit_borough = canonical_borough(display_hit.get("borough")) if isinstance(display_hit, dict) else None
        if hit_borough and valid_nyc_lat_lng(display_hit.get("lat"), display_hit.get("lng")):
            distance = haversine_m(lat, lng, float(display_hit["lat"]), float(display_hit["lng"]))
            if distance <= MAX_NEARBY_METRES:
                proposal.update(
                    {
                        "disposition": "borough_normalized_existing_coordinates",
                        "location_classified": True,
                        "pin_eligible": True,
                        "proposed_borough": hit_borough,
                        "proposed_latitude": lat,
                        "proposed_longitude": lng,
                        "confidence": str(display_hit.get("confidence") or "medium"),
                        "reason": "Gazetteer display match agrees with the existing coordinates.",
                        "evidence_source": display_hit.get("source"),
                        "evidence_distance_m": round(distance, 1),
                    }
                )
                return proposal

        nearby = nearest_borough(spatial_index, lat, lng)
        if nearby and not nearby.get("ambiguous"):
            proposal.update(
                {
                    "disposition": "borough_normalized_existing_coordinates",
                    "location_classified": True,
                    "pin_eligible": True,
                    "proposed_borough": nearby["borough"],
                    "proposed_latitude": lat,
                    "proposed_longitude": lng,
                    "confidence": nearby.get("confidence"),
                    "reason": "Existing coordinates match nearby borough-labelled NYCIF gazetteer evidence.",
                    "evidence_source": nearby.get("source"),
                    "evidence_label": nearby.get("label"),
                    "evidence_distance_m": nearby.get("distance_m"),
                }
            )
            return proposal

        proposal.update(
            {
                "disposition": "unresolved",
                "location_classified": True,
                "pin_eligible": False,
                "reason": nearby.get("reason") if nearby else "Existing coordinates have no unambiguous borough evidence.",
                "ambiguity_candidates": nearby.get("candidates") if nearby else None,
            }
        )
        return proposal

    display_hit = gazetteer.lookup_display(location, text_borough) if location else None
    if isinstance(display_hit, dict) and valid_nyc_lat_lng(display_hit.get("lat"), display_hit.get("lng")):
        proposed_lat = float(display_hit["lat"])
        proposed_lng = float(display_hit["lng"])
        proposed_borough = canonical_borough(display_hit.get("borough")) or text_borough
        if not proposed_borough:
            nearby = nearest_borough(spatial_index, proposed_lat, proposed_lng)
            if nearby and not nearby.get("ambiguous"):
                proposed_borough = nearby.get("borough")
        if proposed_borough:
            proposal.update(
                {
                    "disposition": "mapped_from_gazetteer",
                    "location_classified": True,
                    "pin_eligible": True,
                    "proposed_borough": proposed_borough,
                    "proposed_latitude": proposed_lat,
                    "proposed_longitude": proposed_lng,
                    "confidence": str(display_hit.get("confidence") or "medium"),
                    "reason": str(display_hit.get("confidence_reason") or "NYCIF gazetteer display match."),
                    "evidence_source": display_hit.get("source"),
                    "evidence_label": display_hit.get("label"),
                }
            )
            return proposal

    if resolver is not None and location:
        result = resolver.resolve(display_location=location, borough=text_borough)
        if result.resolved and result.lat is not None and result.lng is not None:
            proposed_borough = text_borough
            nearby = nearest_borough(spatial_index, float(result.lat), float(result.lng))
            if not proposed_borough and nearby and not nearby.get("ambiguous"):
                proposed_borough = nearby.get("borough")
            if proposed_borough:
                proposal.update(
                    {
                        "disposition": "mapped_from_live_geosearch"
                        if result.tier == "tier_3_nyc_geosearch_live"
                        else "mapped_from_gazetteer",
                        "location_classified": True,
                        "pin_eligible": True,
                        "proposed_borough": proposed_borough,
                        "proposed_latitude": float(result.lat),
                        "proposed_longitude": float(result.lng),
                        "confidence": result.confidence or "medium",
                        "reason": result.confidence_reason or "NYC location resolver match.",
                        "evidence_source": result.source,
                        "evidence_label": result.label,
                        "resolver_tier": result.tier,
                    }
                )
                return proposal

    proposal.update(
        {
            "disposition": "unresolved",
            "location_classified": True,
            "pin_eligible": False,
            "proposed_borough": text_borough,
            "reason": (
                "Borough is identifiable from text but coordinates remain unsupported."
                if text_borough
                else "No reliable single-location borough or coordinate evidence was found."
            ),
        }
    )
    return proposal


def build_audit(
    *,
    manifest_path: Path = REVIEW_MANIFEST,
    pages_dir: Path = REVIEW_PAGES,
    allow_live_geosearch: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, review_events = load_review_events(manifest_path, pages_dir)
    targets = [event for event in review_events if canonical_borough(event.get("borough")) is None]

    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        GAZETTEER_PATH.parent.mkdir(parents=True, exist_ok=True)
        GAZETTEER_PATH.write_text(
            json.dumps(build_gazetteer_index(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    spatial_index = build_spatial_index(gazetteer)

    resolver: NYCLocationResolver | None = None
    if allow_live_geosearch:
        cache_payload = load_json(GEOSEARCH_CACHE_PATH, {})
        entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
        resolver = NYCLocationResolver(gazetteer, entries if isinstance(entries, dict) else {}, allow_live_geosearch=True)

    proposals = [
        resolve_null_borough_event(
            event,
            gazetteer=gazetteer,
            spatial_index=spatial_index,
            resolver=resolver,
        )
        for event in targets
    ]
    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in proposals)
    accounted = sum(counts.values())
    proposed_borough = sum(1 for item in proposals if item.get("proposed_borough"))
    proposed_coordinates = sum(
        1
        for item in proposals
        if valid_nyc_lat_lng(item.get("proposed_latitude"), item.get("proposed_longitude"))
    )
    unresolved = counts.get("unresolved", 0)
    report = {
        "artifact_type": "review_location_coverage_audit",
        "generated_at_utc": utc_now(),
        "source_manifest": str(manifest_path.relative_to(ROOT)) if manifest_path.is_relative_to(ROOT) else str(manifest_path),
        "source_generated_at_utc": manifest.get("generated_at_utc"),
        "review_total": len(review_events),
        "target_null_borough_count": len(targets),
        "accounted_count": accounted,
        "location_classified_count": sum(1 for item in proposals if item.get("location_classified") is True),
        "location_classified_pct": round((accounted / len(targets) * 100.0), 4) if targets else 100.0,
        "disposition_counts": dict(sorted(counts.items())),
        "proposed_borough_count": proposed_borough,
        "proposed_coordinate_count": proposed_coordinates,
        "unresolved_count": unresolved,
        "zero_silent_null_borough_records": accounted == len(targets),
        "qa_pass": accounted == len(targets) and all(item.get("disposition") for item in proposals),
        "allow_live_geosearch": allow_live_geosearch,
        "safety": {
            "public_map_modified": False,
            "production_feed_modified": False,
            "location_cache_modified": False,
            "wordpress_modified": False,
            "promotion_allowed": False,
            "proposal_only": True,
        },
    }
    proposal_payload = {
        "artifact_type": "review_location_resolution_proposals",
        "generated_at_utc": report["generated_at_utc"],
        "source_generated_at_utc": report["source_generated_at_utc"],
        "target_count": len(targets),
        "proposals": proposals,
        "safety": report["safety"],
    }
    return report, proposal_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REVIEW_MANIFEST)
    parser.add_argument("--pages-dir", type=Path, default=REVIEW_PAGES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--allow-live-geosearch", action="store_true")
    parser.add_argument("--expected-target-count", type=int)
    args = parser.parse_args()

    allow_live = args.allow_live_geosearch or os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    report, proposals = build_audit(
        manifest_path=args.manifest,
        pages_dir=args.pages_dir,
        allow_live_geosearch=allow_live,
    )
    if args.expected_target_count is not None and report["target_null_borough_count"] != args.expected_target_count:
        report["qa_pass"] = False
        report["expected_target_count"] = args.expected_target_count
        report["target_count_error"] = (
            f"Expected {args.expected_target_count} null-borough records; "
            f"found {report['target_null_borough_count']}."
        )
    write_json(args.report, report)
    write_json(args.proposals, proposals)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
