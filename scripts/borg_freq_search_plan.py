#!/usr/bin/env python3
"""Convert a public-safe FREQ observation into a BORG public-source search plan.

This module does not search the web and does not resolve incident location. It
only produces deterministic, rights-aware search intents over registered public
sources. FREQ remains public-safety truth authority; ENIGMA remains location
authority.
"""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

try:
    from scripts.borg_cli_paths import read_workspace_json, write_workspace_json
except ModuleNotFoundError:  # direct execution from scripts/
    from borg_cli_paths import read_workspace_json, write_workspace_json

CONTRACT = "nycif.borg-freq-public-search-plan.v1"
FORBIDDEN_KEYS = {
    "raw_audio",
    "raw_iq",
    "private_transcript",
    "receiver_exact_location",
    "private_responder_identity",
    "tactical_detail",
    "encryption_key_material",
    "unpublished_exact_incident_coordinates",
}
REQUIRED_KEYS = {
    "freq_observation_id",
    "observed_at",
    "jurisdiction_id",
    "service_class",
    "rights_state",
    "sensitivity_state",
    "location_state",
    "location_evidence_ref",
    "terminology_refs",
    "provenance_ref",
}


def _stable_id(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _terms(observation: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("service_class", "public_area_label"):
        value = observation.get(key)
        if value:
            terms.append(str(value).strip())
    for value in observation.get("public_summary_terms") or []:
        text = str(value).strip()
        if text:
            terms.append(text)
    for value in observation.get("terminology_refs") or []:
        text = str(value).strip()
        if text:
            terms.append(text)
    return list(dict.fromkeys(terms))


def _eligible_source(source: dict[str, Any], jurisdiction_id: str) -> tuple[bool, str | None]:
    rights = source.get("rights") or {}
    if source.get("registration_state") != "ACTIVE":
        return False, "SOURCE_NOT_ACTIVE"
    if source.get("network_scope") != "PUBLIC":
        return False, "NON_PUBLIC_NETWORK_SCOPE"
    if source.get("authentication_mode") == "UNKNOWN":
        return False, "AUTHENTICATION_UNKNOWN"
    if not rights.get("retrieval_allowed") or rights.get("review_state") != "APPROVED":
        return False, "RETRIEVAL_RIGHTS_NOT_APPROVED"
    source_jurisdiction = str(source.get("jurisdiction", "")).upper()
    requested = jurisdiction_id.upper()
    if source_jurisdiction not in {requested, "NYC", "NEW_YORK_CITY", "CITYWIDE"}:
        return False, "JURISDICTION_MISMATCH"
    return True, None


def _validate_observation(observation: dict[str, Any]) -> None:
    present_forbidden = sorted(FORBIDDEN_KEYS.intersection(observation.keys()))
    if present_forbidden:
        raise ValueError(f"FREQ observation contains forbidden bridge fields: {present_forbidden}")
    missing = sorted(REQUIRED_KEYS - observation.keys())
    if missing:
        raise ValueError(f"FREQ observation missing required fields: {missing}")
    if observation["rights_state"] != "PUBLIC_SEARCH_ALLOWED":
        raise ValueError("FREQ observation is not cleared for public-source search")
    if observation["sensitivity_state"] not in {"PUBLIC_SAFE", "NON_TACTICAL"}:
        raise ValueError("FREQ observation sensitivity state is not public-search safe")
    if observation["location_state"] not in {"resolved", "ambiguous", "unresolved", "review_required"}:
        raise ValueError("Unsupported FREQ location state")


def _build_intent(observation: dict[str, Any], source: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    source_id = str(source["source_id"])
    tier = source.get("source_tier")
    purpose = "CORROBORATE_OFFICIAL_PUBLIC_RECORD" if tier in {"A", "B"} else "DISCOVER_CORROBORATING_LEAD"
    exact_location = observation["location_state"] == "resolved" and observation.get("public_location_id")
    location_scope = "EXACT_AUTHORIZED_LOCATION" if exact_location else "AREA_OR_JURISDICTION_ONLY"
    return {
        "intent_id": _stable_id([str(observation["freq_observation_id"]), source_id, purpose, " ".join(terms)]),
        "source_id": source_id,
        "source_tier": tier,
        "canonical_url": source.get("canonical_url"),
        "purpose": purpose,
        "query_terms": terms,
        "time_anchor": observation["observed_at"],
        "location_scope": location_scope,
        "public_area_label": observation.get("public_area_label"),
        "public_location_id": observation.get("public_location_id") if exact_location else None,
        "result_authority": "OBSERVATION_OR_LEAD_ONLY",
        "requires_canonical_followup": True,
    }


def build_search_plan(*, observation: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    _validate_observation(observation)
    terms = _terms(observation)
    if not terms:
        raise ValueError("Search plan requires at least one public-safe search term")

    intents: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    jurisdiction_id = str(observation["jurisdiction_id"])
    ordered_sources = sorted(sources, key=lambda row: (str(row.get("source_tier", "Z")), str(row.get("source_id", ""))))
    for source in ordered_sources:
        source_id = str(source["source_id"])
        eligible, reason = _eligible_source(source, jurisdiction_id)
        if eligible:
            intents.append(_build_intent(observation, source, terms))
        else:
            excluded.append({"source_id": source_id, "reason": str(reason)})

    return {
        "contract": CONTRACT,
        "freq_observation_id": observation["freq_observation_id"],
        "jurisdiction_id": jurisdiction_id,
        "location_state": observation["location_state"],
        "intent_count": len(intents),
        "excluded_source_count": len(excluded),
        "intents": intents,
        "excluded_sources": excluded,
        "authority": {
            "freq_public_safety_truth": "FREQ",
            "source_acquisition": "BORG",
            "geospatial_truth": "ENIGMA / canonical location path",
            "public_runtime": "National Map",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = build_search_plan(
        observation=read_workspace_json(args.observation),
        sources=read_workspace_json(args.sources),
    )
    write_workspace_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
