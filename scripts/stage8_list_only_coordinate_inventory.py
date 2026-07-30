#!/usr/bin/env python3
"""Classify all canonical missing-coordinate records and derive safe proposals.

The canonical target is the projector's complete missing-coordinate queue. The
approved public projection is used only as an immutable index of already
certified map-ready precedents. This pass never mutates production event data
and never calls a network geocoder.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MISSING = ROOT / "data" / "events_discovery_missing_coordinates_v02.json"
APPROVED = ROOT / "data" / "events_discovery_v02_approved.json"
RECONCILIATION = ROOT / "data" / "events_discovery_reconciliation_v02.json"
REPORT = ROOT / "data" / "reports" / "stage8_list_only_coordinate_inventory.json"
PROPOSALS = ROOT / "data" / "reports" / "stage8_list_only_coordinate_proposals.json"
NYC_BOROUGHS = {"bronx", "brooklyn", "manhattan", "queens", "staten island"}


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("events", "items", "records"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
    raise RuntimeError("payload must be a list or contain events/items/records")


def num(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def coords(row: dict[str, Any]) -> tuple[float | None, float | None]:
    return num(row.get("lat", row.get("latitude"))), num(row.get("lng", row.get("longitude")))


def valid_nyc(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and 40.45 <= lat <= 40.95 and -74.30 <= lng <= -73.65


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def approved_status(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return norm(nycif.get("coordinate_status")).replace(" ", "_")


def approved_source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def approved_dataset(row: dict[str, Any]) -> str:
    return str(approved_source(row).get("dataset") or row.get("source_dataset") or "").strip()


def approved_source_id(row: dict[str, Any]) -> str:
    return str(approved_source(row).get("source_event_id") or row.get("source_event_id") or "").strip()


def approved_location(row: dict[str, Any]) -> str:
    return str(row.get("location") or row.get("display_location") or row.get("address") or "").strip()


def target_source(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("source_identity") if isinstance(item.get("source_identity"), dict) else {}


def target_dataset(item: dict[str, Any]) -> str:
    return str(target_source(item).get("dataset") or "").strip()


def target_source_id(item: dict[str, Any]) -> str:
    return str(target_source(item).get("source_event_id") or "").strip()


def target_source_url(item: dict[str, Any]) -> str:
    return str(target_source(item).get("source_url") or "").strip()


def target_location(item: dict[str, Any]) -> str:
    return str(item.get("location") or "").strip()


def target_date(item: dict[str, Any]) -> str:
    return str(item.get("date") or "")[:10]


def fingerprint(item: dict[str, Any]) -> str:
    payload = {
        "canonical_id": str(item.get("canonical_id") or "").strip(),
        "dataset": target_dataset(item),
        "source_event_id": target_source_id(item),
        "date": target_date(item),
        "title": str(item.get("title") or "").strip(),
        "location": target_location(item),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify(item: dict[str, Any]) -> str:
    text = " ".join(norm(item.get(key)) for key in ("title", "location"))
    location = target_location(item)
    if any(token in text for token in ("online event", "virtual event", "zoom", "webinar", "livestream", "live stream")):
        return "online_only"
    if not location:
        return "missing_location_text"
    if re.search(r"\b(new jersey|long island|westchester|connecticut|outside nyc)\b", text):
        return "outside_nyc_or_other"
    return "physical_location_unresolved"


def precedent(row: dict[str, Any]) -> tuple[float, float, str] | None:
    lat, lng = coords(row)
    borough = str(row.get("borough") or "").strip()
    if approved_status(row) != "map_ready" or not valid_nyc(lat, lng) or norm(borough) not in NYC_BOROUGHS:
        return None
    return round(float(lat), 6), round(float(lng), 6), borough


def main() -> int:
    missing_payload = load(MISSING)
    targets = rows(missing_payload)
    approved = rows(load(APPROVED))
    reconciliation = load(RECONCILIATION)
    expected_list = int(reconciliation.get("list_only_coordinate_records") or 0)

    map_rows = [row for row in approved if precedent(row) is not None]
    excluded_map_ready_rows = [
        str(row.get("id") or "")
        for row in approved
        if approved_status(row) == "map_ready" and precedent(row) is None
    ]

    by_source_id: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in map_rows:
        sid = approved_source_id(row)
        if sid:
            by_source_id[(norm(approved_dataset(row)), norm(sid))].append(row)
        location = norm(approved_location(row))
        if location:
            by_location[location].append(row)

    proposals: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    methods: Counter[str] = Counter()

    for item in targets:
        initial_reason = classify(item)
        reason = initial_reason
        proposal: dict[str, Any] | None = None
        dataset = target_dataset(item)
        source_id = target_source_id(item)

        if initial_reason == "physical_location_unresolved":
            candidates = by_source_id.get((norm(dataset), norm(source_id)), []) if source_id else []
            unique = {precedent(candidate) for candidate in candidates if precedent(candidate) is not None}
            if len(unique) == 1:
                lat, lng, borough = next(iter(unique))
                proposal = {
                    "lat": lat,
                    "lng": lng,
                    "borough": borough,
                    "method": "exact_source_event_id_precedent",
                    "evidence_count": len(candidates),
                    "evidence_canonical_ids": sorted(str(candidate.get("id") or "") for candidate in candidates)[:100],
                }

            if proposal is None:
                candidates = by_location.get(norm(target_location(item)), []) if target_location(item) else []
                unique = {precedent(candidate) for candidate in candidates if precedent(candidate) is not None}
                if len(unique) == 1:
                    lat, lng, borough = next(iter(unique))
                    proposal = {
                        "lat": lat,
                        "lng": lng,
                        "borough": borough,
                        "method": "exact_location_precedent",
                        "evidence_count": len(candidates),
                        "evidence_canonical_ids": sorted(str(candidate.get("id") or "") for candidate in candidates)[:100],
                    }

            if proposal is not None:
                reason = "supported_coordinate_proposal"
                methods[proposal["method"]] += 1
                proposals.append(
                    {
                        "canonical_id": str(item.get("canonical_id") or "").strip(),
                        "fingerprint_sha256": fingerprint(item),
                        "source": dataset,
                        "source_event_id": source_id,
                        "source_url": target_source_url(item),
                        "title": item.get("title"),
                        "date": target_date(item),
                        "location": target_location(item),
                        **proposal,
                    }
                )

        reasons[reason] += 1
        ledger.append(
            {
                "canonical_id": str(item.get("canonical_id") or "").strip(),
                "fingerprint_sha256": fingerprint(item),
                "source": dataset,
                "source_event_id": source_id,
                "source_url": target_source_url(item),
                "title": item.get("title"),
                "date": target_date(item),
                "location": target_location(item),
                "current_classification": item.get("current_classification"),
                "reason_code": reason,
                "proposal": proposal,
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    selected_proposals_valid = all(
        valid_nyc(num(item.get("lat")), num(item.get("lng")))
        and norm(item.get("borough")) in NYC_BOROUGHS
        and item.get("method") in {"exact_source_event_id_precedent", "exact_location_precedent"}
        and bool(item.get("evidence_canonical_ids"))
        for item in proposals
    )
    equations = {
        "queue_declared_count_matches_rows": int(missing_payload.get("count") or 0) == len(targets),
        "list_only_matches_reconciliation": len(targets) == expected_list,
        "list_equals_ledger": len(targets) == len(ledger),
        "proposal_count_matches": len(proposals) == reasons.get("supported_coordinate_proposal", 0),
        "all_selected_proposals_valid": selected_proposals_valid,
        "canonical_ids_present_and_unique": len({str(item.get("canonical_id") or "") for item in targets}) == len(targets) and all(item.get("canonical_id") for item in targets),
        "list_fingerprints_unique": len({entry["fingerprint_sha256"] for entry in ledger}) == len(ledger),
        "all_records_reason_coded": sum(reasons.values()) == len(targets),
    }
    qa_pass = all(equations.values())
    report = {
        "artifact_type": "stage8_list_only_coordinate_inventory",
        "schema_version": "2.2.0",
        "generated_at_utc": now,
        "source_snapshot_generated_at_utc": reconciliation.get("generated_at_utc"),
        "approved_projection_total": len(approved),
        "certified_precedent_total": len(map_rows),
        "excluded_existing_map_ready_from_precedent_index_count": len(excluded_map_ready_rows),
        "excluded_existing_map_ready_sample": excluded_map_ready_rows[:100],
        "list_only_total": len(targets),
        "expected_from_reconciliation": {"list_only_total": expected_list},
        "reason_counts": dict(sorted(reasons.items())),
        "proposal_method_counts": dict(sorted(methods.items())),
        "proposal_total": len(proposals),
        "ledger_total": len(ledger),
        "equations": equations,
        "production_data_modified": False,
        "promotion_allowed": False,
        "qa_pass": qa_pass,
        "ledger": ledger,
    }
    write(REPORT, report)
    write(
        PROPOSALS,
        {
            "artifact_type": "stage8_supported_coordinate_proposals",
            "schema_version": "2.2.0",
            "generated_at_utc": now,
            "source_snapshot_generated_at_utc": reconciliation.get("generated_at_utc"),
            "promotion_allowed": False,
            "proposal_total": len(proposals),
            "proposals": proposals,
        },
    )
    print(json.dumps({key: value for key, value in report.items() if key != "ledger"}, indent=2, sort_keys=True))
    if not qa_pass:
        raise RuntimeError("Stage 8 inventory equations failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
