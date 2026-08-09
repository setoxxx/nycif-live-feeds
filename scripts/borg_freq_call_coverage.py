#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

try:
    from scripts.borg_cli_paths import resolve_workspace_file
except ModuleNotFoundError:  # direct execution from scripts/
    from borg_cli_paths import resolve_workspace_file

FORBIDDEN_FIELDS = {
    "raw_audio",
    "raw_iq",
    "private_transcript",
    "receiver_exact_location",
    "private_responder_identity",
    "tactical_detail",
    "encryption_key_material",
    "unpublished_exact_incident_coordinates",
}
LOCATION_STATES = {"resolved", "ambiguous", "unresolved", "review_required"}


def _approved_terms(observation: dict[str, Any], terminology: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for ref in observation.get("terminology_refs") or []:
        term = terminology.get(str(ref))
        if not term:
            continue
        if str(term.get("review_status", "")).lower() != "approved":
            continue
        terms.append(term)
    return sorted(
        terms,
        key=lambda t: (-float(t.get("confidence", 0)), str(t.get("id", ""))),
    )


def _classification(observation: dict[str, Any], terminology: dict[str, dict[str, Any]]) -> dict[str, Any]:
    terms = _approved_terms(observation, terminology)
    if not terms:
        return {
            "classification_state": "PENDING",
            "call_type": "UNKNOWN",
            "call_label": "Public call — classification pending",
            "call_meaning": None,
            "public_summary": "Public call observed; classification pending terminology review.",
            "term_ids": [],
        }
    primary = terms[0]
    return {
        "classification_state": "CLASSIFIED",
        "call_type": primary.get("code") or primary.get("canonical_text") or primary.get("id"),
        "call_label": primary.get("canonical_text") or primary.get("public_summary") or primary.get("id"),
        "call_meaning": primary.get("canonical_meaning"),
        "public_summary": primary.get("public_summary") or primary.get("canonical_meaning"),
        "term_ids": [str(t.get("id")) for t in terms],
    }


def _location(observation: dict[str, Any]) -> dict[str, Any]:
    state = str(observation.get("location_state", "unresolved"))
    if state not in LOCATION_STATES:
        raise ValueError(f"Unsupported location_state: {state}")
    area = observation.get("public_area_label")
    public_location_id = observation.get("public_location_id")
    geometry_state = observation.get("public_geometry_state") or "none"
    geometry = observation.get("public_geometry")

    if state != "resolved":
        public_location_id = None
        geometry = None
        if not area:
            area = "Location not yet resolved"
        if geometry_state == "exact_public":
            geometry_state = "none"
    elif geometry_state == "exact_public" and not public_location_id:
        raise ValueError("resolved exact_public geometry requires public_location_id")

    return {
        "location_state": state,
        "public_area_label": area or "Location not yet resolved",
        "public_location_id": public_location_id,
        "public_geometry_state": geometry_state,
        "public_geometry": geometry,
    }


def project_call_coverage(
    *,
    observations: list[dict[str, Any]],
    terminology_records: list[dict[str, Any]],
) -> dict[str, Any]:
    terminology = {str(row.get("id")): row for row in terminology_records if row.get("id") is not None}
    seen_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    dispositions: Counter[str] = Counter()

    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("Every FREQ observation must be an object")
        forbidden = sorted(FORBIDDEN_FIELDS.intersection(observation.keys()))
        if forbidden:
            disposition = "QUARANTINE_SENSITIVE_INPUT"
            call_id = str(observation.get("freq_observation_id") or "")
            if not call_id or call_id in seen_ids:
                raise ValueError("Sensitive observation still requires a unique freq_observation_id")
            seen_ids.add(call_id)
            records.append({
                "call_id": call_id,
                "observed_at": observation.get("observed_at"),
                "jurisdiction_id": observation.get("jurisdiction_id"),
                "service_class": observation.get("service_class"),
                "classification_state": "WITHHELD",
                "call_type": "WITHHELD",
                "call_label": "Public call record withheld pending sensitive-input review",
                "call_meaning": None,
                "public_summary": "Coverage record retained; sensitive input requires review before public projection.",
                "location_state": "review_required",
                "public_area_label": "Location withheld pending review",
                "public_location_id": None,
                "public_geometry_state": "none",
                "public_geometry": None,
                "coverage_disposition": disposition,
                "provenance_ref": observation.get("provenance_ref"),
                "terminology_refs": [],
            })
            dispositions[disposition] += 1
            continue

        call_id = str(observation.get("freq_observation_id") or "")
        if not call_id:
            raise ValueError("freq_observation_id is required")
        if call_id in seen_ids:
            raise ValueError(f"Duplicate freq_observation_id: {call_id}")
        seen_ids.add(call_id)

        rights_state = str(observation.get("rights_state", "REVIEW_REQUIRED")).upper()
        sensitivity_state = str(observation.get("sensitivity_state", "REVIEW_REQUIRED")).upper()
        classification = _classification(observation, terminology)
        location = _location(observation)

        if rights_state not in {"PUBLIC", "APPROVED", "CLEARED"}:
            disposition = "RIGHTS_REVIEW_REQUIRED"
        elif sensitivity_state not in {"PUBLIC", "NORMAL", "CLEARED", "NON_TACTICAL"}:
            disposition = "SENSITIVITY_REVIEW_REQUIRED"
        elif classification["classification_state"] == "PENDING":
            disposition = "CLASSIFICATION_PENDING_PUBLIC"
        elif location["location_state"] != "resolved":
            disposition = "CLASSIFIED_PUBLIC_LOCATION_PENDING"
        else:
            disposition = "CLASSIFIED_PUBLIC"

        record = {
            "call_id": call_id,
            "observed_at": observation.get("observed_at"),
            "jurisdiction_id": observation.get("jurisdiction_id"),
            "service_class": observation.get("service_class"),
            **classification,
            **location,
            "coverage_disposition": disposition,
            "provenance_ref": observation.get("provenance_ref"),
            "terminology_refs": classification["term_ids"],
        }
        record.pop("term_ids", None)
        records.append(record)
        dispositions[disposition] += 1

    records.sort(key=lambda r: (str(r.get("observed_at") or ""), r["call_id"]))
    return {
        "contract": "nycif.borg-freq-call-coverage-projection.v1",
        "records": records,
        "accounting": {
            "input_observation_count": len(observations),
            "terminal_record_count": len(records),
            "nature_filtered_count": 0,
            "silent_loss": len(observations) - len(records),
            "dispositions": dict(sorted(dispositions.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", required=True)
    parser.add_argument("--terminology", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    observations_path = resolve_workspace_file(args.observations, must_exist=True)
    terminology_path = resolve_workspace_file(args.terminology, must_exist=True)
    output_path = resolve_workspace_file(args.output, must_exist=False)
    observations_payload = json.loads(observations_path.read_text())
    terminology_payload = json.loads(terminology_path.read_text())
    observations = observations_payload.get("records", observations_payload)
    terminology_records = terminology_payload.get("records", terminology_payload)
    result = project_call_coverage(observations=observations, terminology_records=terminology_records)
    output_path.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
