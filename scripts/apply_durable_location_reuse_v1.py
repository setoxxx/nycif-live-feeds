#!/usr/bin/env python3
"""Apply the NYCIF resolve-once/reuse-forever location rule.

A current standalone public occurrence may reuse a durable registry location only
when its normalized source location, borough, and alias identity resolve to one
unambiguous stored location. Exact stored places may restore MAP_READY exact pins.
Approximate stored places remain GENERAL_AREA and can never become certified.
Street-route claims remain in the dedicated route lane.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.sync_supabase_location_registry_v1 import alias_source_datasets
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from nyc_location_resolver import coordinate_matches_borough  # type: ignore[no-redef]
    from sync_supabase_location_registry_v1 import alias_source_datasets  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
REGISTRY = Path("/tmp/nycif-location-registry-v1.json")
REPORT = ROOT / "data" / "durable_location_reuse_v1_report.json"
AUTHORITY = "durable_location_registry_v1"
STREET_SEGMENT_RE = re.compile(r"\bbetween\b.+\band\b|\bfrom\b.+\bto\b", re.IGNORECASE)


def normalize_alias(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return (
        str(row.get("source_dataset") or source.get("dataset") or "").strip(),
        str(row.get("source_event_id") or source.get("source_event_id") or "").strip(),
    )


def source_location(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(
        nycif.get("source_location_text")
        or row.get("event_location")
        or row.get("location")
        or row.get("display_location")
        or row.get("address")
        or ""
    ).strip()


def standalone_public(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return (
        row.get("event_role") == "public_event"
        and row.get("parent_event_id") in (None, "")
        and str(nycif.get("display_disposition") or "") in {"standalone_public_event", "list_only", "approximate_marker"}
    )


def already_exact(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return nycif.get("map_eligibility_state") == "MAP_READY" and nycif.get("certified_pin") is True


def load_registry(path: Path) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str], set[str]], dict[tuple[str, str], set[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "NYCIF_LOCATION_REGISTRY_RUNTIME_V1":
        raise RuntimeError("unexpected durable location registry schema")
    locations = {
        str(row.get("location_id")): row
        for row in payload.get("locations", [])
        if isinstance(row, dict) and row.get("location_id")
    }
    dataset_index: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    borough_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for alias in payload.get("aliases", []):
        if not isinstance(alias, dict):
            continue
        loc_id = str(alias.get("location_id") or "")
        location = locations.get(loc_id)
        normalized = normalize_alias(alias.get("normalized_alias") or alias.get("raw_alias"))
        borough = normalize_alias(location.get("borough") if location else "")
        if not loc_id or not normalized or not borough or location is None:
            continue
        for dataset in alias_source_datasets(alias):
            dataset_index[(normalized, dataset, borough)].add(loc_id)
        borough_index[(normalized, borough)].add(loc_id)
    return locations, dataset_index, borough_index


def non_circular_source_authority(stored: dict[str, Any]) -> str:
    """Keep the authority that originally certified the stored place.

    Reuse may observe ``durable_location_registry_v1``, but that token must not
    be written back as the source of the stored location. If the stored row has
    no non-circular original, leave the occurrence unstamped rather than invent
    provenance. Exact vs approximate reuse lanes stay independent of this check.
    """
    metadata = stored.get("metadata") if isinstance(stored.get("metadata"), dict) else {}
    for candidate in (
        stored.get("location_authority"),
        metadata.get("original_location_authority"),
        metadata.get("source_location_authority"),
        stored.get("location_reuse_source_authority"),
        metadata.get("location_reuse_source_authority"),
    ):
        text = str(candidate or "").strip()
        if text and text != AUTHORITY:
            return text
    return ""


def choose_location(
    normalized: str,
    dataset: str,
    borough: str,
    dataset_index: dict[tuple[str, str, str], set[str]],
    borough_index: dict[tuple[str, str], set[str]],
) -> tuple[str | None, str]:
    dataset_matches = dataset_index.get((normalized, dataset, borough), set()) if dataset else set()
    if len(dataset_matches) == 1:
        return next(iter(dataset_matches)), "dataset_borough_alias"
    if len(dataset_matches) > 1:
        return None, "ambiguous_dataset_borough_alias"
    borough_matches = borough_index.get((normalized, borough), set())
    if len(borough_matches) == 1:
        return next(iter(borough_matches)), "borough_alias"
    if len(borough_matches) > 1:
        return None, "ambiguous_borough_alias"
    return None, "no_registry_match"


def apply(canonical_path: Path = CANONICAL, registry_path: Path = REGISTRY, report_path: Path = REPORT) -> dict[str, Any]:
    canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical = [row for row in extract_rows(canonical_payload) if isinstance(row, dict)]
    locations, dataset_index, borough_index = load_registry(registry_path)

    match_basis_counts: Counter[str] = Counter()
    precision_counts: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    exact_reused = 0
    approximate_reused = 0
    missing_source_authority_reused = 0
    invalid = 0

    for event in canonical:
        if not standalone_public(event):
            skipped["not_standalone_public"] += 1
            continue
        if already_exact(event):
            skipped["already_exact"] += 1
            continue
        raw = source_location(event)
        normalized = normalize_alias(raw)
        borough = normalize_alias(event.get("borough"))
        dataset, _ = source_parts(event)
        if not raw or not normalized or not borough:
            skipped["missing_match_identity"] += 1
            continue
        if STREET_SEGMENT_RE.search(normalized):
            skipped["street_route_claim"] += 1
            continue

        location_id, basis = choose_location(normalized, dataset, borough, dataset_index, borough_index)
        match_basis_counts[basis] += 1
        if not location_id:
            skipped[basis] += 1
            continue
        stored = locations[location_id]
        lat = finite(stored.get("latitude"))
        lng = finite(stored.get("longitude"))
        precision = str(stored.get("precision") or "")
        if lat is None or lng is None or precision not in {"exact", "approximate"}:
            skipped["stored_geometry_unusable"] += 1
            continue
        if not coordinate_matches_borough(lat, lng, str(event.get("borough") or "")):
            skipped["stored_borough_geometry_conflict"] += 1
            continue

        nycif = event.setdefault("nycif", {})
        event["latitude"] = lat
        event["longitude"] = lng
        event["location"] = raw
        event["location_id"] = location_id
        nycif["location_id"] = location_id
        nycif["source_location_text"] = raw
        nycif["location_authority"] = AUTHORITY
        nycif["location_reuse_match_basis"] = basis
        original = non_circular_source_authority(stored)
        if original:
            nycif["location_reuse_source_authority"] = original
        else:
            nycif.pop("location_reuse_source_authority", None)
            missing_source_authority_reused += 1
        nycif["location_reuse_registry_precision"] = precision

        if precision == "exact":
            event["location_evidence"] = {
                "tier": "exact_site",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": f"durable_registry:{location_id}",
                "reason_code": "DURABLE_LOCATION_REGISTRY_EXACT_REUSE",
                "reason_detail": "Previously verified durable location reused for a new occurrence with the same unambiguous alias and borough identity.",
            }
            nycif["coordinate_status"] = "map_ready"
            nycif["map_eligibility_state"] = "MAP_READY"
            nycif["certified_pin"] = True
            nycif["display_disposition"] = "standalone_public_event"
            nycif["pin_precision"] = "exact"
            nycif["pin_integrity_reason"] = "DURABLE_LOCATION_REGISTRY_EXACT_REUSE"
            exact_reused += 1
        else:
            event["location_evidence"] = {
                "tier": "approximate_area",
                "validation_state": "validated",
                "exact_pin_eligible": False,
                "source_provenance": f"durable_registry:{location_id}",
                "reason_code": "DURABLE_LOCATION_REGISTRY_APPROXIMATE_REUSE",
                "reason_detail": "Previously stored approximate location reused without granting exact-site authority.",
            }
            nycif["coordinate_status"] = "approximate"
            nycif["map_eligibility_state"] = "GENERAL_AREA"
            nycif["certified_pin"] = False
            nycif["display_disposition"] = "approximate_marker"
            nycif["pin_precision"] = "approximate"
            nycif["pin_integrity_reason"] = "DURABLE_LOCATION_REGISTRY_APPROXIMATE_REUSE"
            approximate_reused += 1
        precision_counts[precision] += 1

    for event in canonical:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        if nycif.get("location_authority") != AUTHORITY:
            continue
        lat = finite(event.get("latitude"))
        lng = finite(event.get("longitude"))
        precision = nycif.get("location_reuse_registry_precision")
        evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
        if lat is None or lng is None or not coordinate_matches_borough(lat, lng, str(event.get("borough") or "")):
            invalid += 1
            continue
        if precision == "exact":
            if not (
                nycif.get("map_eligibility_state") == "MAP_READY"
                and nycif.get("certified_pin") is True
                and evidence.get("exact_pin_eligible") is True
            ):
                invalid += 1
        elif precision == "approximate":
            if not (
                nycif.get("map_eligibility_state") == "GENERAL_AREA"
                and nycif.get("certified_pin") is False
                and evidence.get("exact_pin_eligible") is False
            ):
                invalid += 1
        else:
            invalid += 1

    report = {
        "schema_version": "NYCIF_DURABLE_LOCATION_REUSE_V1",
        "authority": AUTHORITY,
        "canonical_rows": len(canonical),
        "registry_location_count": len(locations),
        "dataset_alias_keys": len(dataset_index),
        "borough_alias_keys": len(borough_index),
        "exact_reused_count": exact_reused,
        "approximate_reused_count": approximate_reused,
        "total_reused_count": exact_reused + approximate_reused,
        "missing_source_authority_reused_count": missing_source_authority_reused,
        "precision_counts": dict(sorted(precision_counts.items())),
        "match_basis_counts": dict(sorted(match_basis_counts.items())),
        "skipped_counts": dict(sorted(skipped.items())),
        "invalid_reuse_count": invalid,
        "ambiguous_promotions": 0,
        "route_point_promotions": 0,
        "qa_pass": invalid == 0,
        "operating_rule": "Resolve once, certify once, store durably, match aliases, reuse automatically, and revalidate only on conflict or authority change.",
    }

    if isinstance(canonical_payload, list):
        output_payload: Any = canonical
    else:
        output_payload = canonical_payload
        for key in ("events", "rows", "items", "records", "occurrences", "data"):
            if isinstance(output_payload.get(key), list):
                output_payload[key] = canonical
                break
    canonical_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["qa_pass"]:
        raise RuntimeError(f"durable location reuse QA failed: {report}")
    return report


def main() -> int:
    apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
