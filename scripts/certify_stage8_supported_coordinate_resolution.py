#!/usr/bin/env python3
"""Certify the Stage 8 supported-coordinate production rebuild."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROPOSALS = ROOT / "data" / "reports" / "stage8_list_only_coordinate_proposals.json"
APPLY = ROOT / "data" / "reports" / "stage8_supported_coordinate_apply_report.json"
RECON = ROOT / "data" / "events_discovery_reconciliation_v02.json"
MISSING = ROOT / "data" / "events_discovery_missing_coordinates_v02.json"
APPROVED = ROOT / "data" / "events_discovery_v02_approved.json"
REVIEW = ROOT / "data" / "events_discovery_v02_review.json"
CERTIFICATE = ROOT / "data" / "reports" / "stage8_supported_coordinate_resolution_certificate.json"
EXPECTED_ACCEPTED = 36322
EXPECTED_PROMOTED = 632
EXPECTED_LIST_ONLY = 365
EXPECTED_MAP_READY = 35957


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    return []


def num(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    proposals_payload = load(PROPOSALS)
    proposals = proposals_payload.get("proposals") if isinstance(proposals_payload, dict) else []
    apply = load(APPLY)
    reconciliation = load(RECON)
    missing_payload = load(MISSING)
    missing_rows = rows(missing_payload)
    output_rows = rows(load(APPROVED)) + rows(load(REVIEW))
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in output_rows:
        by_id.setdefault(str(row.get("id") or ""), []).append(row)

    missing_ids = {str(item.get("canonical_id") or "") for item in missing_rows}
    unresolved_promoted = []
    missing_output = []
    coordinate_mismatches = []
    for proposal in proposals:
        canonical_id = str(proposal.get("canonical_id") or "")
        if canonical_id in missing_ids:
            unresolved_promoted.append(canonical_id)
        matches = by_id.get(canonical_id, [])
        if not matches:
            missing_output.append(canonical_id)
            continue
        expected_lat = round(float(proposal["lat"]), 6)
        expected_lng = round(float(proposal["lng"]), 6)
        exact = False
        for row in matches:
            nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
            lat = num(row.get("latitude", row.get("lat")))
            lng = num(row.get("longitude", row.get("lng")))
            if (
                nycif.get("coordinate_status") == "map_ready"
                and lat is not None
                and lng is not None
                and round(lat, 6) == expected_lat
                and round(lng, 6) == expected_lng
                and str(row.get("borough") or "") == str(proposal.get("borough") or "")
            ):
                exact = True
                break
        if not exact:
            coordinate_mismatches.append(canonical_id)

    equations = {
        "proposal_total_exact": len(proposals) == EXPECTED_PROMOTED,
        "apply_total_exact": int(apply.get("applied_total") or 0) == EXPECTED_PROMOTED,
        "apply_qa_pass": apply.get("qa_pass") is True,
        "accepted_total_unchanged": int(reconciliation.get("accepted_canonical_records") or 0) == EXPECTED_ACCEPTED,
        "list_only_reduced_exactly": int(reconciliation.get("list_only_coordinate_records") or -1) == EXPECTED_LIST_ONLY,
        "map_ready_increased_exactly": int(reconciliation.get("map_ready_records") or -1) == EXPECTED_MAP_READY,
        "strict_reconciliation_pass": reconciliation.get("reconciles_strict") is True,
        "missing_queue_count_exact": int(missing_payload.get("count") or -1) == EXPECTED_LIST_ONLY == len(missing_rows),
        "no_promoted_id_remains_missing": not unresolved_promoted,
        "all_promoted_ids_emitted": not missing_output,
        "all_promoted_coordinates_exact": not coordinate_mismatches,
        "accepted_equals_map_plus_list": EXPECTED_ACCEPTED == EXPECTED_MAP_READY + EXPECTED_LIST_ONLY,
    }
    qa_pass = all(equations.values())
    certificate = {
        "artifact_type": "stage8_supported_coordinate_resolution_certificate",
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "baseline": {
            "accepted": EXPECTED_ACCEPTED,
            "map_ready": EXPECTED_MAP_READY - EXPECTED_PROMOTED,
            "list_only": EXPECTED_LIST_ONLY + EXPECTED_PROMOTED,
        },
        "result": {
            "accepted": reconciliation.get("accepted_canonical_records"),
            "map_ready": reconciliation.get("map_ready_records"),
            "list_only": reconciliation.get("list_only_coordinate_records"),
            "promoted": len(proposals),
        },
        "remaining_reason_contract": "365 unsupported records remain list-only and retain Stage 8 inventory reason codes; no coordinates invented",
        "unresolved_promoted_count": len(unresolved_promoted),
        "missing_output_count": len(missing_output),
        "coordinate_mismatch_count": len(coordinate_mismatches),
        "unresolved_promoted_sample": unresolved_promoted[:100],
        "missing_output_sample": missing_output[:100],
        "coordinate_mismatch_sample": coordinate_mismatches[:100],
        "equations": equations,
        "qa_pass": qa_pass,
    }
    write(CERTIFICATE, certificate)
    print(json.dumps(certificate, indent=2, sort_keys=True))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
