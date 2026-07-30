#!/usr/bin/env python3
"""Classify every canonical approved list-only coordinate record.

This Stage 8 pass is intentionally read-only. It emits coordinate proposals only
when the current immutable approved snapshot already contains one unambiguous,
map-ready precedent. It never mutates event data and never calls a network
geocoder. A separate fail-closed promotion pass is required.
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
    raise RuntimeError("approved feed must be a list or contain events/items/records")


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


def nested(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if value not in (None, ""):
        return value
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return nycif.get(key)


def first(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = nested(row, key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def source_id(row: dict[str, Any]) -> str:
    src = source(row)
    return first(row, ("source_event_id", "event_id")) or str(src.get("source_event_id") or src.get("event_id") or "").strip()


def source_name(row: dict[str, Any]) -> str:
    src = source(row)
    return first(row, ("source_dataset", "source_name", "source_slug")) or str(src.get("dataset") or src.get("name") or src.get("slug") or "").strip()


def source_url(row: dict[str, Any]) -> str:
    src = source(row)
    return first(row, ("source_url", "url", "permalink", "link")) or str(src.get("source_url") or src.get("url") or "").strip()


def location(row: dict[str, Any]) -> str:
    return first(row, ("display_location", "location", "event_location", "address", "venue"))


def event_date(row: dict[str, Any]) -> str:
    return first(row, ("event_date", "date", "start_date", "start_date_time", "start"))[:10]


def coordinate_status(row: dict[str, Any]) -> str:
    return norm(nested(row, "coordinate_status")).replace(" ", "_")


def display_disposition(row: dict[str, Any]) -> str:
    return norm(nested(row, "display_disposition")).replace(" ", "_")


def canonical_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "canonical_id": canonical_id(row),
        "dataset": source_name(row),
        "source_event_id": source_id(row),
        "date": event_date(row),
        "title": str(row.get("title") or "").strip(),
        "borough": str(row.get("borough") or "").strip(),
        "location": location(row),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify(row: dict[str, Any]) -> str:
    text = " ".join(
        norm(nested(row, key))
        for key in ("title", "location", "display_location", "address", "venue", "description")
    )
    role = norm(row.get("event_role") or row.get("role")).replace(" ", "_")
    disposition = display_disposition(row)
    borough = norm(row.get("borough"))
    if any(token in text for token in ("online event", "virtual event", "zoom", "webinar", "livestream", "live stream")):
        return "online_only"
    if role == "private_or_reserved_activity" or disposition == "private_or_reserved_activity":
        return "private_or_reserved"
    if borough == "other":
        return "outside_nyc_or_other"
    if not location(row):
        return "missing_location_text"
    return "physical_location_unresolved"


def precedent_tuple(row: dict[str, Any]) -> tuple[float, float, str] | None:
    lat, lng = coords(row)
    borough = norm(row.get("borough"))
    if not valid_nyc(lat, lng) or borough not in NYC_BOROUGHS:
        return None
    return round(float(lat), 6), round(float(lng), 6), str(row.get("borough")).strip()


def main() -> int:
    events = rows(load(APPROVED))
    reconciliation = load(RECONCILIATION)
    expected_total = int(reconciliation.get("accepted_canonical_records") or 0)
    expected_map = int(reconciliation.get("map_ready_records") or 0)
    expected_list = int(reconciliation.get("list_only_coordinate_records") or 0)

    statuses = Counter(coordinate_status(row) for row in events)
    unknown_status = [row for row in events if coordinate_status(row) not in {"map_ready", "list_only"}]
    map_rows = [row for row in events if coordinate_status(row) == "map_ready"]
    list_rows = [row for row in events if coordinate_status(row) == "list_only"]
    invalid_map_rows = [canonical_id(row) for row in map_rows if precedent_tuple(row) is None]

    by_source_id: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_location: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in map_rows:
        if precedent_tuple(row) is None:
            continue
        sid = source_id(row)
        if sid:
            by_source_id[(norm(source_name(row)), norm(sid))].append(row)
        loc = norm(location(row))
        borough = norm(row.get("borough"))
        if loc and borough in NYC_BOROUGHS:
            by_location[(loc, borough)].append(row)

    proposals: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    methods: Counter[str] = Counter()

    for row in list_rows:
        initial_reason = classify(row)
        reason = initial_reason
        proposal: dict[str, Any] | None = None
        sid = source_id(row)

        # Only physical, public, NYC-location candidates may receive a proposal.
        if initial_reason == "physical_location_unresolved":
            candidates = by_source_id.get((norm(source_name(row)), norm(sid)), []) if sid else []
            unique = {precedent_tuple(candidate) for candidate in candidates if precedent_tuple(candidate) is not None}
            method = ""
            if len(unique) == 1:
                lat, lng, borough = next(iter(unique))
                method = "exact_source_event_id_precedent"
                proposal = {
                    "lat": lat,
                    "lng": lng,
                    "borough": borough,
                    "method": method,
                    "evidence_count": len(candidates),
                    "evidence_canonical_ids": sorted(canonical_id(candidate) for candidate in candidates)[:100],
                }

            if proposal is None:
                location_key = (norm(location(row)), norm(row.get("borough")))
                candidates = by_location.get(location_key, []) if all(location_key) else []
                unique = {precedent_tuple(candidate) for candidate in candidates if precedent_tuple(candidate) is not None}
                if len(unique) == 1:
                    lat, lng, borough = next(iter(unique))
                    method = "exact_location_borough_precedent"
                    proposal = {
                        "lat": lat,
                        "lng": lng,
                        "borough": borough,
                        "method": method,
                        "evidence_count": len(candidates),
                        "evidence_canonical_ids": sorted(canonical_id(candidate) for candidate in candidates)[:100],
                    }

            if proposal is not None:
                reason = "supported_coordinate_proposal"
                methods[proposal["method"]] += 1
                proposals.append(
                    {
                        "canonical_id": canonical_id(row),
                        "fingerprint_sha256": fingerprint(row),
                        "source": source_name(row),
                        "source_event_id": sid,
                        "source_url": source_url(row),
                        "title": row.get("title"),
                        "date": event_date(row),
                        "borough": row.get("borough"),
                        "location": location(row),
                        **proposal,
                    }
                )

        reasons[reason] += 1
        ledger.append(
            {
                "canonical_id": canonical_id(row),
                "fingerprint_sha256": fingerprint(row),
                "source": source_name(row),
                "source_event_id": sid,
                "source_url": source_url(row),
                "title": row.get("title"),
                "date": event_date(row),
                "borough": row.get("borough"),
                "location": location(row),
                "event_role": row.get("event_role"),
                "display_disposition": display_disposition(row),
                "reason_code": reason,
                "proposal": proposal,
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    equations = {
        "approved_matches_reconciliation": len(events) == expected_total,
        "map_ready_matches_reconciliation": len(map_rows) == expected_map,
        "list_only_matches_reconciliation": len(list_rows) == expected_list,
        "approved_equals_map_plus_list": len(events) == len(map_rows) + len(list_rows),
        "list_equals_ledger": len(list_rows) == len(ledger),
        "proposal_count_matches": len(proposals) == reasons.get("supported_coordinate_proposal", 0),
        "all_statuses_known": not unknown_status,
        "all_map_ready_coordinates_valid": not invalid_map_rows,
        "canonical_ids_unique": len({canonical_id(row) for row in events}) == len(events),
        "list_fingerprints_unique": len({item["fingerprint_sha256"] for item in ledger}) == len(ledger),
    }
    qa_pass = all(equations.values())
    report = {
        "artifact_type": "stage8_list_only_coordinate_inventory",
        "schema_version": "2.0.0",
        "generated_at_utc": now,
        "source_snapshot_generated_at_utc": reconciliation.get("generated_at_utc"),
        "approved_total": len(events),
        "map_ready_total": len(map_rows),
        "list_only_total": len(list_rows),
        "expected_from_reconciliation": {
            "approved_total": expected_total,
            "map_ready_total": expected_map,
            "list_only_total": expected_list,
        },
        "coordinate_status_counts": dict(sorted(statuses.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "proposal_method_counts": dict(sorted(methods.items())),
        "proposal_total": len(proposals),
        "ledger_total": len(ledger),
        "invalid_map_ready_count": len(invalid_map_rows),
        "invalid_map_ready_sample": invalid_map_rows[:100],
        "unknown_status_count": len(unknown_status),
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
            "schema_version": "2.0.0",
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
