#!/usr/bin/env python3
"""Build the reader-safe approximate-marker overlay from final canonical state.

The approximate overlay is intentionally separate from exact MAP_READY geometry.
Durable-registry rows may legitimately resolve either to exact or approximate
geometry. Exact durable rows belong exclusively to the exact reader and are
therefore excluded here, not counted as invalid approximate markers.

For rows that do claim the approximate lane, publication remains fail-closed:
GENERAL_AREA, non-certified evidence, borough containment, unique occurrence
identity, and the approved authority contract are all required.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from nyc_location_resolver import coordinate_matches_borough  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
RECOVERY_REPORT = ROOT / "data" / "approximate_marker_recovery_v1_report.json"
REUSE_REPORT = ROOT / "data" / "durable_location_reuse_v1_report.json"
OUT = ROOT / "data" / "reader-safe" / "approximate-marker-recovery-v1.geojson"
STATUS = ROOT / "data" / "reader-safe" / "approximate-marker-recovery-v1-status.json"
RECOVERY_AUTHORITY = "projector_v3_approximate_recovery_v1"
DURABLE_AUTHORITY = "durable_location_registry_v1"
ALLOWED_AUTHORITIES = {RECOVERY_AUTHORITY, DURABLE_AUTHORITY}


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in extract_rows(payload) if isinstance(row, dict)]


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def source_parts(row: dict[str, Any]) -> tuple[str | None, str | None]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return source.get("dataset"), source.get("source_event_id")


def final_approximate_contract(event: dict[str, Any]) -> tuple[bool, str]:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    authority = str(nycif.get("location_authority") or "")
    state = str(nycif.get("map_eligibility_state") or "")
    certified = nycif.get("certified_pin") is True

    # Durable reuse can legitimately recover an exact location. That row is
    # already validated by the exact reader and must never enter this overlay.
    if authority == DURABLE_AUTHORITY and state == "MAP_READY" and certified:
        return False, "durable_exact_lane"
    if authority not in ALLOWED_AUTHORITIES:
        return False, "authority_not_approximate_lane"

    lat = finite(event.get("latitude"))
    lng = finite(event.get("longitude"))
    borough = str(event.get("borough") or "").strip()
    evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
    valid = (
        lat is not None
        and lng is not None
        and bool(borough)
        and coordinate_matches_borough(lat, lng, borough)
        and state == "GENERAL_AREA"
        and nycif.get("coordinate_status") == "approximate"
        and nycif.get("certified_pin") is False
        and evidence.get("tier") == "approximate_area"
        and evidence.get("validation_state") == "validated"
        and evidence.get("exact_pin_eligible") is False
    )
    return (valid, "final_approximate" if valid else "invalid_approximate_contract")


def build(
    canonical_path: Path = CANONICAL,
    recovery_report_path: Path = RECOVERY_REPORT,
    reuse_report_path: Path = REUSE_REPORT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    canonical = load_rows(canonical_path)
    recovery = json.loads(recovery_report_path.read_text(encoding="utf-8"))
    reuse = (
        json.loads(reuse_report_path.read_text(encoding="utf-8"))
        if reuse_report_path.exists()
        else {}
    )
    features: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()
    skip_counts: Counter[str] = Counter()
    invalid = 0
    ids: set[str] = set()
    final_contract_count = 0

    for event in canonical:
        valid, reason = final_approximate_contract(event)
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        authority = str(nycif.get("location_authority") or "")
        if reason in {"authority_not_approximate_lane", "durable_exact_lane"}:
            skip_counts[reason] += 1
            continue
        if not valid:
            invalid += 1
            continue
        final_contract_count += 1
        occurrence = "|".join(str(part) for part in occurrence_key_v2(event))
        if occurrence in ids:
            invalid += 1
            continue
        ids.add(occurrence)
        lat = float(event["latitude"])
        lng = float(event["longitude"])
        dataset, source_event_id = source_parts(event)
        source_counts[str(dataset or "unknown")] += 1
        authority_counts[authority] += 1
        features.append(
            {
                "type": "Feature",
                "id": occurrence,
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "occurrence_id": occurrence,
                    "location_id": event.get("location_id") or nycif.get("location_id"),
                    "title": event.get("title"),
                    "location": event.get("location"),
                    "borough": event.get("borough"),
                    "start_date_time": event.get("start_date_time"),
                    "end_date_time": event.get("end_date_time"),
                    "source_dataset": dataset,
                    "source_event_id": source_event_id,
                    "marker_precision": "approximate",
                    "certified_pin": False,
                    "map_eligibility_state": "GENERAL_AREA",
                    "location_authority": authority,
                    "location_reuse_source_authority": nycif.get("location_reuse_source_authority"),
                    "approximate_recovery_reason": nycif.get("approximate_recovery_reason"),
                },
            }
        )

    duplicate_count = final_contract_count - len(ids)
    recovery_count = int(recovery.get("recovered_approximate_markers") or 0)
    reuse_count = int(reuse.get("approximate_reused_count") or 0) if reuse else 0
    exact_reuse_count = int(reuse.get("exact_reused_count") or 0) if reuse else 0
    durable_exact_excluded = int(skip_counts.get("durable_exact_lane", 0))
    counts_match_final_contract = len(features) == final_contract_count
    exact_reuse_lane_reconciles = durable_exact_excluded == exact_reuse_count
    status = {
        "schema_version": "NYCIF_APPROXIMATE_MARKER_READER_V3_PRECISION_LANES",
        "generated_at_utc": generated,
        "authorities": sorted(ALLOWED_AUTHORITIES),
        "authority_counts": dict(sorted(authority_counts.items())),
        "approximate_marker_count": len(features),
        "final_contract_count": final_contract_count,
        "counts_match_final_contract": counts_match_final_contract,
        "invalid_marker_count": invalid,
        "duplicate_occurrence_count": duplicate_count,
        "exact_pin_count": 0,
        "source_counts": dict(sorted(source_counts.items())),
        "skip_counts": dict(sorted(skip_counts.items())),
        "durable_exact_excluded_count": durable_exact_excluded,
        "durable_exact_report_count": exact_reuse_count,
        "durable_exact_lane_reconciles": exact_reuse_lane_reconciles,
        "recovery_report_count": recovery_count,
        "durable_reuse_report_count": reuse_count,
        "recovery_count_is_diagnostic_only": True,
        "qa_pass": (
            invalid == 0
            and duplicate_count == 0
            and counts_match_final_contract
            and exact_reuse_lane_reconciles
        ),
        "operating_rule": (
            "Exact durable locations are owned by the exact reader and excluded from the approximate overlay. "
            "Final canonical GENERAL_AREA geometry owns approximate publication; approximate markers never grant certified exact pins."
        ),
    }
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "NYCIF_APPROXIMATE_MARKER_READER_V3_PRECISION_LANES",
            "generated_at_utc": generated,
            "authorities": sorted(ALLOWED_AUTHORITIES),
            "marker_precision": "approximate",
            "final_contract_count": final_contract_count,
            "durable_exact_excluded_count": durable_exact_excluded,
        },
        "features": features,
    }
    return geojson, status


def main() -> int:
    geojson, status = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(geojson, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2, sort_keys=True))
    if not status["qa_pass"]:
        raise RuntimeError(f"approximate reader overlay QA failed: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
