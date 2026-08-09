#!/usr/bin/env python3
"""Build the exhaustive Wave A Pin Recovery inventory (read-only).

The inventory is deliberately evidence-first. It compares the freshly rebuilt
Projector V3 canonical corpus with a separately checked-out historical READY
public-feed snapshot, but historical coordinates are never promoted by this
script. They are evidence candidates only.

Every current standalone public occurrence that is not MAP_READY receives one
explicit recovery disposition. Deterministic local resolver evidence may be
recorded as immediately reproducible only when the canonical resolver itself
returns validated, exact-pin-eligible evidence. Live GeoSearch is disabled.

Outputs:
- data/reports/NYC_EVENT_HISTORICAL_PIN_RECONCILIATION_V1.json
- data/reports/NYC_EVENT_PIN_RECOVERY_QUEUE_V1.json
- data/reports/NYC_EVENT_PIN_RECOVERY_REASON_CENSUS_V1.json

This script never mutates canonical events, source snapshots, the location cache,
or any public map artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.nyc_location_resolver import NYCLocationResolver, coordinate_matches_borough
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from nyc_location_resolver import NYCLocationResolver, coordinate_matches_borough  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
REPORT_DIR = ROOT / "data" / "reports"
HISTORICAL_OUT = REPORT_DIR / "NYC_EVENT_HISTORICAL_PIN_RECONCILIATION_V1.json"
QUEUE_OUT = REPORT_DIR / "NYC_EVENT_PIN_RECOVERY_QUEUE_V1.json"
CENSUS_OUT = REPORT_DIR / "NYC_EVENT_PIN_RECOVERY_REASON_CENSUS_V1.json"
SCHEMA_VERSION = "1.0.0"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(payload: Any) -> list[dict[str, Any]]:
    try:
        return [row for row in extract_rows(payload) if isinstance(row, dict)]
    except Exception:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("events", "items", "records", "features"):
                value = payload.get(key)
                if isinstance(value, list):
                    out: list[dict[str, Any]] = []
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        if key == "features" and isinstance(item.get("properties"), dict):
                            merged = dict(item["properties"])
                            geometry = item.get("geometry")
                            if isinstance(geometry, dict) and geometry.get("type") == "Point":
                                coords = geometry.get("coordinates") or []
                                if isinstance(coords, list) and len(coords) >= 2:
                                    merged.setdefault("longitude", coords[0])
                                    merged.setdefault("latitude", coords[1])
                            out.append(merged)
                        else:
                            out.append(item)
                    return out
        return []


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def text(value: Any) -> str:
    return str(value or "").strip()


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text(value).lower()).strip()


def finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = text(row.get("source_dataset") or source.get("dataset"))
    source_id = text(
        row.get("source_event_id")
        or source.get("source_event_id")
        or source.get("event_id")
    )
    return dataset, source_id


def start_value(row: dict[str, Any]) -> str:
    for key in ("start_date_time", "start", "date", "start_date"):
        value = text(row.get(key))
        if value:
            return value
    return ""


def day(value: Any) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text(value))
    return match.group(1) if match else ""


def identity_tuple(row: dict[str, Any]) -> tuple[str, str, str]:
    dataset, source_id = source_parts(row)
    try:
        key = occurrence_key_v2(row)
        return tuple(text(part) for part in key)  # type: ignore[return-value]
    except Exception:
        return dataset, source_id, start_value(row)


def identity_string(row: dict[str, Any]) -> str:
    return "|".join(identity_tuple(row))


def day_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    dataset, source_id = source_parts(row)
    return dataset, source_id, day(start_value(row))


def coordinates(row: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = finite(row.get("latitude"))
    if lat is None:
        lat = finite(row.get("lat"))
    lng = finite(row.get("longitude"))
    if lng is None:
        lng = finite(row.get("lng"))
    if lng is None:
        lng = finite(row.get("lon"))
    return lat, lng


def evidence(row: dict[str, Any]) -> dict[str, Any]:
    direct = row.get("location_evidence")
    if isinstance(direct, dict):
        return direct
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    nested = nycif.get("location_evidence")
    return nested if isinstance(nested, dict) else {}


def evidence_validated_exact(row: dict[str, Any]) -> bool:
    item = evidence(row)
    return (
        normalized(item.get("validation_state")) == "validated"
        and item.get("exact_pin_eligible") is True
        and bool(
            item.get("source_provenance")
            or item.get("geocoder_provenance")
            or item.get("source")
            or item.get("provider")
            or item.get("geocoder_source")
        )
    )


def map_state(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return text(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "REVIEW_REQUIRED")


def certified_pin(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return nycif.get("certified_pin") is True or row.get("certified_pin") is True


def standalone_public(row: dict[str, Any]) -> bool:
    if text(row.get("event_role")) != "public_event":
        return False
    if row.get("parent_event_id") not in (None, ""):
        return False
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    disposition = text(nycif.get("display_disposition"))
    return disposition in {"standalone_public_event", "list_only"}


def public_url(row: dict[str, Any]) -> str | None:
    for key in ("public_url", "permalink", "link", "website", "url"):
        value = text(row.get(key))
        if value.lower().startswith(("http://", "https://")):
            return value
    return None


def location_text(row: dict[str, Any]) -> str:
    value = row.get("location") or row.get("display_location") or row.get("address") or ""
    if isinstance(value, dict):
        value = " ".join(
            text(value.get(key))
            for key in ("name", "display_name", "address", "street", "description")
        )
    return text(value)


def fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "occurrence_id": identity_string(row),
        "title": text(row.get("title")),
        "location": location_text(row),
        "borough": text(row.get("borough")),
        "start": start_value(row),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def historical_rows(root: Path) -> list[dict[str, Any]]:
    candidates = [
        root / "data" / "events_discovery_v02_approved.json",
        root / "data" / "schema-v1-discovery" / "approved" / "events.json",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size:
            parsed = rows(load(path))
            if parsed:
                return parsed

    page_dir = root / "data" / "schema-v1-discovery" / "approved" / "pages"
    collected: list[dict[str, Any]] = []
    if page_dir.exists():
        for path in sorted(page_dir.glob("*.json")):
            collected.extend(rows(load(path)))
    return collected


def historical_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    lat, lng = coordinates(row)
    if lat is None or lng is None:
        return None
    dataset, source_id = source_parts(row)
    return {
        "historical_id": row.get("id"),
        "source_dataset": dataset,
        "source_event_id": source_id,
        "start": start_value(row),
        "day": day(start_value(row)),
        "title": row.get("title"),
        "location": location_text(row),
        "borough": row.get("borough"),
        "latitude": lat,
        "longitude": lng,
        "historical_coordinate_status": (
            (row.get("nycif") or {}).get("coordinate_status")
            if isinstance(row.get("nycif"), dict)
            else row.get("coordinate_status")
        ),
    }


def resolver_candidate(resolver: NYCLocationResolver, row: dict[str, Any]) -> dict[str, Any] | None:
    location = location_text(row)
    borough = text(row.get("borough")) or None
    if not location:
        return None
    result = resolver.resolve(display_location=location, borough=borough)
    lat = finite(result.lat)
    lng = finite(result.lng)
    if (
        not result.resolved
        or lat is None
        or lng is None
        or normalized(result.validation_state) != "validated"
        or result.exact_pin_eligible is not True
    ):
        return None
    if borough and not coordinate_matches_borough(lat, lng, borough):
        return None
    return {
        "latitude": lat,
        "longitude": lng,
        "tier": result.tier,
        "validation_state": result.validation_state,
        "exact_pin_eligible": result.exact_pin_eligible,
        "source_provenance": result.source,
        "confidence": result.confidence,
        "confidence_reason": result.confidence_reason,
        "reason_code": result.reason_code,
        "reason_detail": result.reason_detail,
        "label": result.label,
        "query_used": result.query_used,
    }


def unique_points(items: Iterable[dict[str, Any]]) -> set[tuple[float, float]]:
    out: set[tuple[float, float]] = set()
    for item in items:
        lat, lng = coordinates(item)
        if lat is not None and lng is not None:
            out.add((round(lat, 7), round(lng, 7)))
    return out


def classify(
    current: dict[str, Any],
    exact_history: list[dict[str, Any]],
    day_history: list[dict[str, Any]],
    resolver_exact: dict[str, Any] | None,
) -> tuple[str, str, bool]:
    if not location_text(current):
        return "MISSING_LOCATION_TEXT", "No public location text is available; preserve LIST_ONLY.", False
    if evidence_validated_exact(current):
        return (
            "CURRENT_VALIDATED_EVIDENCE_AUTHORITY_CONFLICT",
            "Current occurrence carries validated exact evidence but is not MAP_READY; review publication-state conflict rather than inventing new location evidence.",
            False,
        )
    if resolver_exact is not None:
        return (
            "REPRODUCIBLE_CANONICAL_RESOLVER_EXACT",
            "Canonical local resolver reproduced validated exact evidence without live geocoding; eligible for a separate Projector V3 application candidate.",
            True,
        )
    exact_points = unique_points(exact_history)
    if len(exact_points) == 1:
        return (
            "HISTORICAL_EXACT_OCCURRENCE_CANDIDATE",
            "One historical exact-occurrence coordinate exists. It is evidence-only until current authority independently reproduces it.",
            False,
        )
    if len(exact_points) > 1:
        return (
            "HISTORICAL_EXACT_OCCURRENCE_CONFLICT",
            "Historical exact-occurrence evidence contains multiple coordinate assertions; preserve review state.",
            False,
        )
    day_points = unique_points(day_history)
    if len(day_points) == 1:
        return (
            "HISTORICAL_DAY_PRECISION_CANDIDATE",
            "A same-source same-day historical coordinate exists without exact-start continuity; evidence-only, no automatic reuse.",
            False,
        )
    if len(day_points) > 1:
        return (
            "HISTORICAL_DAY_PRECISION_CONFLICT",
            "Same-source same-day historical evidence contains multiple coordinates; preserve review state.",
            False,
        )
    return "NO_REPRODUCIBLE_EXACT_EVIDENCE", "No current reproducible exact evidence was found; preserve searchable non-marker state.", False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--historical-root",
        type=Path,
        required=True,
        help="Read-only checkout of a prior READY public-feed commit.",
    )
    args = parser.parse_args()

    canonical = rows(load(CANONICAL))
    current_nonmarkers = [
        row
        for row in canonical
        if standalone_public(row)
        and not (map_state(row) == "MAP_READY" and certified_pin(row))
    ]

    historical = historical_rows(args.historical_root.resolve())
    hist_exact: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    hist_day: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    hist_with_coords = 0
    for row in historical:
        candidate = historical_candidate(row)
        if candidate is None:
            continue
        hist_with_coords += 1
        hist_exact[identity_tuple(row)].append(row)
        hist_day[day_identity(row)].append(row)

    resolver = NYCLocationResolver.load_default()
    # This inventory must be deterministic and read-only. Never allow the
    # resolver to issue live network requests from this pass.
    resolver.allow_live_geosearch = False

    reason_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    queue: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    reproducible = 0

    for row in current_nonmarkers:
        exact_history = hist_exact.get(identity_tuple(row), [])
        same_day_history = hist_day.get(day_identity(row), [])
        resolver_exact = resolver_candidate(resolver, row)
        reason, explanation, immediately_reproducible = classify(
            row, exact_history, same_day_history, resolver_exact
        )
        reason_counts[reason] += 1
        state_counts[map_state(row)] += 1
        dataset, source_id = source_parts(row)
        source_counts[dataset or "UNSPECIFIED"] += 1
        reproducible += int(immediately_reproducible)

        exact_candidates = [item for item in (historical_candidate(x) for x in exact_history) if item]
        day_candidates = [item for item in (historical_candidate(x) for x in same_day_history) if item]
        entry = {
            "canonical_id": row.get("id"),
            "occurrence_id": identity_string(row),
            "fingerprint_sha256": fingerprint(row),
            "source_dataset": dataset,
            "source_event_id": source_id,
            "title": row.get("title"),
            "aliases": row.get("aliases") or [],
            "venue": row.get("venue") or row.get("facility_name"),
            "location": location_text(row) or None,
            "borough": row.get("borough"),
            "zip": row.get("zip") or row.get("zipcode"),
            "category": row.get("category"),
            "start_date_time": row.get("start_date_time"),
            "end_date_time": row.get("end_date_time"),
            "timezone": row.get("timezone"),
            "public_url": public_url(row),
            "current_map_state": map_state(row),
            "current_certified_pin": certified_pin(row),
            "current_location_evidence": evidence(row) or None,
            "recovery_reason": reason,
            "recovery_explanation": explanation,
            "immediately_reproducible_under_current_authority": immediately_reproducible,
            "canonical_resolver_candidate": resolver_exact,
            "historical_exact_occurrence_candidates": exact_candidates,
            "historical_day_precision_candidates": day_candidates,
            "promotion_allowed": False,
            "public_map_modified": False,
            "identity_modified": False,
            "temporal_state_modified": False,
        }
        queue.append(entry)
        reconciliation.append(
            {
                "occurrence_id": entry["occurrence_id"],
                "canonical_id": entry["canonical_id"],
                "recovery_reason": reason,
                "historical_exact_match_count": len(exact_candidates),
                "historical_day_match_count": len(day_candidates),
                "resolver_exact_reproduced": resolver_exact is not None,
                "identity_modified": False,
                "temporal_state_modified": False,
            }
        )

    queue.sort(key=lambda item: (
        0 if item["immediately_reproducible_under_current_authority"] else 1,
        item["recovery_reason"],
        text(item.get("start_date_time")),
        text(item.get("source_dataset")),
        text(item.get("source_event_id")),
    ))
    reconciliation.sort(key=lambda item: text(item.get("occurrence_id")))

    current_ids = [entry["occurrence_id"] for entry in queue]
    equations = {
        "every_current_nonmarker_dispositioned": len(queue) == len(current_nonmarkers),
        "current_nonmarker_occurrence_ids_unique": len(current_ids) == len(set(current_ids)),
        "reason_counts_balance": sum(reason_counts.values()) == len(queue),
        "reconciliation_balances_queue": len(reconciliation) == len(queue),
        "no_identity_mutation": all(entry["identity_modified"] is False for entry in queue),
        "no_temporal_mutation": all(entry["temporal_state_modified"] is False for entry in queue),
        "no_public_map_mutation": all(entry["public_map_modified"] is False for entry in queue),
        "no_inventory_promotion": all(entry["promotion_allowed"] is False for entry in queue),
        "resolver_live_calls_zero": int(getattr(resolver, "_live_calls", 0)) == 0,
    }
    qa_pass = all(equations.values())
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    history_payload = {
        "artifact_type": "NYC_EVENT_HISTORICAL_PIN_RECONCILIATION_V1",
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "historical_root": str(args.historical_root),
        "historical_rows_loaded": len(historical),
        "historical_rows_with_coordinates": hist_with_coords,
        "current_canonical_rows": len(canonical),
        "current_nonmarker_standalone_public_rows": len(current_nonmarkers),
        "operating_rule": "Historical coordinates are evidence candidates only; no historical point grants MAP_READY.",
        "identity_authority": "OccurrenceIdentityV2",
        "location_authority": "Projector V3 semantic_map_decision",
        "equations": equations,
        "qa_pass": qa_pass,
        "reconciliation": reconciliation,
    }
    queue_payload = {
        "artifact_type": "NYC_EVENT_PIN_RECOVERY_QUEUE_V1",
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "queue_total": len(queue),
        "immediately_reproducible_high_confidence": reproducible,
        "promotion_allowed": False,
        "operating_rule": "Inventory first. Apply only separately certified current evidence; unresolved events remain reader-visible without exact geometry.",
        "queue": queue,
    }
    census_payload = {
        "artifact_type": "NYC_EVENT_PIN_RECOVERY_REASON_CENSUS_V1",
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "queue_total": len(queue),
        "current_map_state_counts": dict(sorted(state_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "immediately_reproducible_high_confidence": reproducible,
        "rejected_or_held_for_review": len(queue) - reproducible,
        "qa_pass": qa_pass,
        "equations": equations,
    }

    write(HISTORICAL_OUT, history_payload)
    write(QUEUE_OUT, queue_payload)
    write(CENSUS_OUT, census_payload)
    print(json.dumps({
        "qa_pass": qa_pass,
        "current_canonical_rows": len(canonical),
        "queue_total": len(queue),
        "immediately_reproducible_high_confidence": reproducible,
        "reason_counts": dict(sorted(reason_counts.items())),
        "resolver_live_calls": int(getattr(resolver, "_live_calls", 0)),
    }, indent=2, sort_keys=True))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
