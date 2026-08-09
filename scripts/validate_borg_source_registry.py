#!/usr/bin/env python3
"""Fail-closed validation for BORG source registry records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CONTRACT = "nycif.borg-source-registry.v1"
SOURCE_TIERS = {"A", "B", "C", "D"}
SOURCE_TYPES = {"API", "DATASET", "RSS", "ICS", "JSON_FEED", "PUBLIC_DOWNLOAD", "HTML_PAGE", "MANUAL_VERIFIED"}
AUTHORITY_CLASSES = {
    "AUTHORITATIVE_GEOGRAPHY",
    "AUTHORITATIVE_AGGREGATE_STATISTICS",
    "OFFICIAL_OBSERVATION",
    "SUPPORTING_ASSERTION",
    "DISCOVERY_ONLY",
}
AUTH_MODES = {"NONE", "PUBLIC_API_KEY", "APP_TOKEN", "OAUTH", "MANUAL", "UNKNOWN"}
NETWORK_SCOPES = {"PUBLIC", "PRIVATE", "LOOPBACK", "LINK_LOCAL", "UNKNOWN"}
HEALTH_STATES = {"HEALTHY", "DEGRADED", "FAILED", "UNKNOWN"}
REGISTRATION_STATES = {"ACTIVE", "PAUSED", "REVIEW_REQUIRED", "PROHIBITED", "RETIRED"}
REVIEW_STATES = {"APPROVED", "REVIEW_REQUIRED", "PROHIBITED"}
PAGINATION_MODES = {"NONE", "OFFSET_LIMIT", "CURSOR", "PAGE", "LINK_HEADER", "SOURCE_SPECIFIC", "UNKNOWN"}
BACKOFF_MODES = {"BOUNDED_EXPONENTIAL", "BOUNDED_LINEAR", "NONE"}
REQUIRED = {
    "source_id",
    "provider",
    "source_tier",
    "authority_class",
    "jurisdiction",
    "source_type",
    "canonical_url",
    "authentication_mode",
    "cadence",
    "freshness_sla_hours",
    "native_id_strategy",
    "schema_fingerprint",
    "parser_version",
    "rights",
    "network_scope",
    "pagination",
    "retry_policy",
    "health",
    "provenance",
    "registration_state",
}


def _fail(message: str) -> None:
    raise ValueError(message)


def validate_registry(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract") != CONTRACT:
        _fail("Unsupported source registry contract")
    records = payload.get("records")
    if not isinstance(records, list):
        _fail("Source registry records must be a list")

    source_ids: set[str] = set()
    states: Counter[str] = Counter()
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            _fail(f"Source registry row {index} must be an object")
        missing = sorted(REQUIRED - row.keys())
        if missing:
            _fail(f"Source registry row {index} missing fields: {missing}")

        source_id = str(row["source_id"]).strip()
        if not source_id:
            _fail(f"Source registry row {index} has empty source_id")
        if source_id in source_ids:
            _fail(f"Duplicate source_id: {source_id}")
        source_ids.add(source_id)

        if row["source_tier"] not in SOURCE_TIERS:
            _fail(f"{source_id}: invalid source_tier")
        if row["source_type"] not in SOURCE_TYPES:
            _fail(f"{source_id}: invalid source_type")
        if row["authority_class"] not in AUTHORITY_CLASSES:
            _fail(f"{source_id}: invalid authority_class")
        if row["authentication_mode"] not in AUTH_MODES:
            _fail(f"{source_id}: invalid authentication_mode")
        if row["network_scope"] not in NETWORK_SCOPES:
            _fail(f"{source_id}: invalid network_scope")
        if row["health"] not in HEALTH_STATES:
            _fail(f"{source_id}: invalid health")
        if row["registration_state"] not in REGISTRATION_STATES:
            _fail(f"{source_id}: invalid registration_state")
        states[row["registration_state"]] += 1
        is_active = row["registration_state"] == "ACTIVE"

        parsed = urlparse(str(row["canonical_url"]))
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            _fail(f"{source_id}: canonical_url must be absolute HTTP(S)")
        if is_active:
            if parsed.scheme != "https":
                _fail(f"{source_id}: active automated source must use HTTPS")
            if row["network_scope"] != "PUBLIC":
                _fail(f"{source_id}: active source must have PUBLIC network scope")
            if row["authentication_mode"] == "UNKNOWN":
                _fail(f"{source_id}: active source cannot have UNKNOWN authentication")
            if row["health"] == "UNKNOWN":
                _fail(f"{source_id}: active source cannot have UNKNOWN health")
            if not str(row["schema_fingerprint"]).strip():
                _fail(f"{source_id}: active source requires schema_fingerprint")
            if not str(row["parser_version"]).strip():
                _fail(f"{source_id}: active source requires parser_version")

        rights = row["rights"]
        if not isinstance(rights, dict):
            _fail(f"{source_id}: rights must be object")
        for field in ("retrieval_allowed", "retention_allowed", "transformation_allowed", "public_projection_allowed", "attribution_required", "review_state"):
            if field not in rights:
                _fail(f"{source_id}: rights missing {field}")
        if rights["review_state"] not in REVIEW_STATES:
            _fail(f"{source_id}: invalid rights review_state")
        if is_active:
            if rights["review_state"] != "APPROVED" or rights["retrieval_allowed"] is not True:
                _fail(f"{source_id}: active source requires approved retrieval rights")
            if row["source_tier"] == "D" and rights["public_projection_allowed"] is True:
                _fail(f"{source_id}: Tier D source cannot independently allow public projection")

        pagination = row["pagination"]
        if not isinstance(pagination, dict):
            _fail(f"{source_id}: pagination must be object")
        for field in ("mode", "deterministic_ordering", "exhaustion_or_total_parity_required"):
            if field not in pagination:
                _fail(f"{source_id}: pagination missing {field}")
        if pagination["mode"] not in PAGINATION_MODES:
            _fail(f"{source_id}: invalid pagination mode")
        if is_active:
            if pagination["mode"] == "UNKNOWN":
                _fail(f"{source_id}: active source cannot have UNKNOWN pagination")
            if pagination["mode"] != "NONE" and pagination["deterministic_ordering"] is not True:
                _fail(f"{source_id}: paginated source requires deterministic ordering")
            if pagination["mode"] != "NONE" and pagination["exhaustion_or_total_parity_required"] is not True:
                _fail(f"{source_id}: paginated source requires exhaustion/total parity")

        retry = row["retry_policy"]
        if not isinstance(retry, dict):
            _fail(f"{source_id}: retry_policy must be object")
        for field in ("max_attempts", "backoff", "retryable_status_classes"):
            if field not in retry:
                _fail(f"{source_id}: retry_policy missing {field}")
        if retry["backoff"] not in BACKOFF_MODES:
            _fail(f"{source_id}: invalid retry backoff")
        attempts = int(retry["max_attempts"])
        if attempts < 0 or attempts > 10:
            _fail(f"{source_id}: max_attempts must be between 0 and 10")
        freshness = float(row["freshness_sla_hours"])
        if freshness <= 0:
            _fail(f"{source_id}: freshness_sla_hours must be positive")

    return {
        "contract": CONTRACT,
        "source_count": len(records),
        "registration_state_accounting": {state: states.get(state, 0) for state in sorted(REGISTRATION_STATES)},
        "active_count": states.get("ACTIVE", 0),
        "zero_silent_loss": sum(states.values()) == len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry")
    args = parser.parse_args()
    summary = validate_registry(json.loads(Path(args.registry).read_text()))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
