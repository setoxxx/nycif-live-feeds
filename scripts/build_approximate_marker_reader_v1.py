#!/usr/bin/env python3
"""Build a reader-safe approximate-marker overlay from canonical V3 events.

This overlay is intentionally separate from the exact MapLibre V3 source. Every
feature here is a non-certified approximate point produced by
``projector_v3_approximate_recovery_v1``. Exact MAP_READY semantics remain owned
by ``national-map-events-v03.geojson``.
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
OUT = ROOT / "data" / "reader-safe" / "approximate-marker-recovery-v1.geojson"
STATUS = ROOT / "data" / "reader-safe" / "approximate-marker-recovery-v1-status.json"
AUTHORITY = "projector_v3_approximate_recovery_v1"


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


def main() -> int:
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    canonical = load_rows(CANONICAL)
    recovery = json.loads(RECOVERY_REPORT.read_text(encoding="utf-8"))
    features: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    invalid = 0
    ids: set[str] = set()

    for event in canonical:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        if nycif.get("location_authority") != AUTHORITY:
            continue
        lat = finite(event.get("latitude"))
        lng = finite(event.get("longitude"))
        borough = str(event.get("borough") or "").strip()
        evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
        occurrence = "|".join(str(part) for part in occurrence_key_v2(event))
        valid = (
            lat is not None
            and lng is not None
            and bool(borough)
            and coordinate_matches_borough(lat, lng, borough)
            and nycif.get("map_eligibility_state") == "GENERAL_AREA"
            and nycif.get("coordinate_status") == "approximate"
            and nycif.get("certified_pin") is False
            and evidence.get("tier") == "approximate_area"
            and evidence.get("validation_state") == "validated"
            and evidence.get("exact_pin_eligible") is False
            and occurrence not in ids
        )
        if not valid:
            invalid += 1
            continue
        ids.add(occurrence)
        dataset, source_event_id = source_parts(event)
        source_counts[str(dataset or "unknown")] += 1
        features.append(
            {
                "type": "Feature",
                "id": occurrence,
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "occurrence_id": occurrence,
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
                    "location_authority": AUTHORITY,
                    "approximate_recovery_reason": nycif.get("approximate_recovery_reason"),
                },
            }
        )

    status = {
        "schema_version": "NYCIF_APPROXIMATE_MARKER_READER_V1",
        "generated_at_utc": generated,
        "authority": AUTHORITY,
        "approximate_marker_count": len(features),
        "invalid_marker_count": invalid,
        "duplicate_occurrence_count": len(features) - len(ids),
        "exact_pin_count": 0,
        "source_counts": dict(sorted(source_counts.items())),
        "recovery_report_count": int(recovery.get("recovered_approximate_markers") or 0),
        "counts_match_recovery": len(features) == int(recovery.get("recovered_approximate_markers") or 0),
        "qa_pass": invalid == 0 and len(features) == int(recovery.get("recovered_approximate_markers") or 0),
        "operating_rule": "Approximate markers are visually distinct and never count as certified exact pins.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "metadata": {
                    "schema_version": "NYCIF_APPROXIMATE_MARKER_READER_V1",
                    "generated_at_utc": generated,
                    "authority": AUTHORITY,
                    "marker_precision": "approximate",
                },
                "features": features,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    STATUS.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2, sort_keys=True))
    if not status["qa_pass"]:
        raise RuntimeError(f"approximate reader overlay QA failed: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
