#!/usr/bin/env python3
"""Recover evidence-backed approximate event markers after Projector V3.

This lane is deliberately distinct from exact MAP_READY authority.

A current standalone public occurrence may receive an APPROXIMATE marker only
when the current semantic-intake transaction already matched the exact current
source location to a prior coordinate under the legacy migration audit and the
match passed borough containment. Known street-segment/route claims are never
converted into point markers here.

The lane never sets ``certified_pin`` and never grants ``MAP_READY``. Its sole
purpose is to restore useful map placement while preserving V3's exact-site
truth contract.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from gps_identity import normalize_text_legacy  # type: ignore[no-redef]
    from nyc_location_resolver import coordinate_matches_borough  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
SEMANTIC = ROOT / "data" / "nycif_live_test_enriched_events.json"
REPORT = ROOT / "data" / "approximate_marker_recovery_v1_report.json"
AUTHORITY = "projector_v3_approximate_recovery_v1"
ALLOWED_REASONS = {
    "FACILITY_SITE_VALIDATION_REQUIRED",
    "ADDRESS_CANONICAL_RERESOLUTION_REQUIRED",
    "INTERSECTION_CANONICAL_RERESOLUTION_REQUIRED",
    "CURRENT_LOCATION_CLAIM_NOT_EXACT_TIER",
}
STREET_SEGMENT_RE = re.compile(r"\bbetween\b.+\band\b", re.IGNORECASE)


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in extract_rows(payload) if isinstance(row, dict)]


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def text(value: Any) -> str:
    return str(value or "").strip()


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return (
        text(row.get("source_dataset") or source.get("dataset")),
        text(row.get("source_event_id") or source.get("source_event_id")),
    )


def location_text(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return text(
        nycif.get("source_location_text")
        or row.get("event_location")
        or row.get("location")
        or row.get("display_location")
        or row.get("address")
    )


def identity(row: dict[str, Any]) -> tuple[str, str, str]:
    try:
        return tuple(str(part) for part in occurrence_key_v2(row))  # type: ignore[return-value]
    except Exception:
        dataset, source_event_id = source_parts(row)
        start = text(row.get("start_date_time") or row.get("start"))
        return dataset, source_event_id, start


def identity_day(key: tuple[str, str, str]) -> tuple[str, str, str]:
    return key[0], key[1], key[2][:10]


def standalone_public(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return (
        text(row.get("event_role")) == "public_event"
        and row.get("parent_event_id") in (None, "")
        and text(nycif.get("display_disposition")) in {"standalone_public_event", "list_only", "approximate_marker"}
    )


def already_exact(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return nycif.get("map_eligibility_state") == "MAP_READY" and nycif.get("certified_pin") is True


def candidate_from_semantic(row: dict[str, Any]) -> dict[str, Any] | None:
    reason = text(row.get("location_evidence_migration_reason"))
    if reason not in ALLOWED_REASONS:
        return None
    loc = location_text(row)
    if not loc or STREET_SEGMENT_RE.search(normalize_text_legacy(loc)):
        return None
    lat = finite(row.get("lat", row.get("latitude")))
    lng = finite(row.get("lng", row.get("longitude")))
    borough = text(row.get("borough") or row.get("event_borough"))
    if lat is None or lng is None or not borough or not coordinate_matches_borough(lat, lng, borough):
        return None
    return {
        "latitude": lat,
        "longitude": lng,
        "location": loc,
        "borough": borough,
        "migration_reason": reason,
        "source_provenance": text(
            row.get("location_source")
            or row.get("coordinate_source")
            or row.get("geocoder_source")
            or "current_source_prior_coordinate_agreement"
        ),
    }


def build_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    conflicts: set[tuple[str, str, str]] = set()
    for row in rows:
        candidate = candidate_from_semantic(row)
        if candidate is None:
            continue
        key = identity(row)
        if key in index:
            previous = index[key]
            if (
                round(float(previous["latitude"]), 7),
                round(float(previous["longitude"]), 7),
            ) != (
                round(float(candidate["latitude"]), 7),
                round(float(candidate["longitude"]), 7),
            ):
                conflicts.add(key)
        else:
            index[key] = candidate
    for key in conflicts:
        index.pop(key, None)
    return index


def apply() -> dict[str, Any]:
    canonical = load_rows(CANONICAL)
    semantic = load_rows(SEMANTIC)
    candidates = build_index(semantic)
    candidate_sources = {(key[0], key[1]) for key in candidates}
    candidate_days = {identity_day(key) for key in candidates}
    source_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    eligibility_counts: Counter[str] = Counter()
    recovered = 0
    location_mismatch = 0
    borough_mismatch = 0
    route_blocked = 0

    for event in canonical:
        if not standalone_public(event):
            eligibility_counts["not_standalone_public"] += 1
            continue
        if already_exact(event):
            eligibility_counts["already_exact"] += 1
            continue
        eligibility_counts["eligible_non_exact"] += 1
        event_location = location_text(event)
        if STREET_SEGMENT_RE.search(normalize_text_legacy(event_location)):
            route_blocked += 1
            continue
        key = identity(event)
        candidate = candidates.get(key)
        if candidate is None:
            eligibility_counts["no_exact_identity_candidate"] += 1
            if (key[0], key[1]) in candidate_sources:
                eligibility_counts["source_identity_candidate_exists"] += 1
            if identity_day(key) in candidate_days:
                eligibility_counts["same_day_candidate_exists"] += 1
            continue
        eligibility_counts["exact_identity_candidate_match"] += 1
        if normalize_text_legacy(event_location) != normalize_text_legacy(candidate["location"]):
            location_mismatch += 1
            continue
        event_borough = text(event.get("borough"))
        if not event_borough or event_borough.casefold() != text(candidate["borough"]).casefold():
            borough_mismatch += 1
            continue
        lat = float(candidate["latitude"])
        lng = float(candidate["longitude"])
        if not coordinate_matches_borough(lat, lng, event_borough):
            borough_mismatch += 1
            continue

        nycif = event.setdefault("nycif", {})
        event["latitude"] = lat
        event["longitude"] = lng
        event["location_evidence"] = {
            "tier": "approximate_area",
            "validation_state": "validated",
            "exact_pin_eligible": False,
            "source_provenance": candidate["source_provenance"],
            "reason_code": "CURRENT_SOURCE_LOCATION_MATCHED_PRIOR_POINT_APPROXIMATE",
            "reason_detail": (
                "Current official source location and borough agree with a previously stored point. "
                "The point is restored only as an approximate marker; exact-site certification remains pending."
            ),
        }
        nycif["coordinate_status"] = "approximate"
        nycif["map_eligibility_state"] = "GENERAL_AREA"
        nycif["certified_pin"] = False
        nycif["display_disposition"] = "approximate_marker"
        nycif["location_authority"] = AUTHORITY
        nycif["pin_precision"] = "approximate"
        nycif["pin_integrity_reason"] = "CURRENT_SOURCE_LOCATION_MATCHED_PRIOR_POINT_APPROXIMATE"
        nycif["approximate_recovery_reason"] = candidate["migration_reason"]
        recovered += 1
        dataset, _ = source_parts(event)
        source_counts[dataset] += 1
        reason_counts[candidate["migration_reason"]] += 1

    invalid = 0
    for event in canonical:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        if nycif.get("location_authority") != AUTHORITY:
            continue
        lat = finite(event.get("latitude"))
        lng = finite(event.get("longitude"))
        borough = text(event.get("borough"))
        evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
        if (
            nycif.get("map_eligibility_state") != "GENERAL_AREA"
            or nycif.get("coordinate_status") != "approximate"
            or nycif.get("display_disposition") != "approximate_marker"
            or nycif.get("certified_pin") is not False
            or evidence.get("tier") != "approximate_area"
            or evidence.get("exact_pin_eligible") is not False
            or lat is None
            or lng is None
            or not borough
            or not coordinate_matches_borough(lat, lng, borough)
            or STREET_SEGMENT_RE.search(normalize_text_legacy(location_text(event)))
        ):
            invalid += 1

    report = {
        "schema_version": "NYCIF_APPROXIMATE_MARKER_RECOVERY_V1",
        "authority": AUTHORITY,
        "canonical_rows": len(canonical),
        "semantic_rows": len(semantic),
        "candidate_occurrences": len(candidates),
        "candidate_source_keys": len(candidate_sources),
        "candidate_day_keys": len(candidate_days),
        "eligibility_counts": dict(sorted(eligibility_counts.items())),
        "recovered_approximate_markers": recovered,
        "source_counts": dict(sorted(source_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "route_claims_blocked_from_point_recovery": route_blocked,
        "location_mismatch_count": location_mismatch,
        "borough_mismatch_count": borough_mismatch,
        "invalid_approximate_marker_count": invalid,
        "exact_pin_promotions": 0,
        "qa_pass": invalid == 0 and location_mismatch == 0 and borough_mismatch == 0,
        "operating_rule": (
            "Approximate markers may improve map placement, but they never grant MAP_READY or certified_pin. "
            "Street routes/segments are excluded from point recovery."
        ),
    }
    CANONICAL.write_text(json.dumps(canonical, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["qa_pass"]:
        raise RuntimeError(f"approximate marker recovery failed: {report}")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
