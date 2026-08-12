#!/usr/bin/env python3
"""Fail-closed validation for BORG source registry records."""

from __future__ import annotations

import argparse
import ipaddress
from collections import Counter
from typing import Any
from urllib.parse import urlparse

try:
    from scripts.borg_cli_paths import read_workspace_json
except ModuleNotFoundError:  # direct execution from scripts/
    from borg_cli_paths import read_workspace_json

CONTRACT = "nycif.borg-source-registry.v1"
SOURCE_TIERS = {"A", "B", "C", "D"}
SOURCE_TYPES = {"API", "DATASET", "RSS", "ICS", "JSON_FEED", "PUBLIC_DOWNLOAD", "HTML_PAGE", "MANUAL_VERIFIED"}
AUTHORITY_CLASSES = {"AUTHORITATIVE_GEOGRAPHY", "AUTHORITATIVE_AGGREGATE_STATISTICS", "OFFICIAL_OBSERVATION", "SUPPORTING_ASSERTION", "DISCOVERY_ONLY"}
AUTH_MODES = {"NONE", "PUBLIC_API_KEY", "APP_TOKEN", "OAUTH", "MANUAL", "UNKNOWN"}
NETWORK_SCOPES = {"PUBLIC", "PRIVATE", "LOOPBACK", "LINK_LOCAL", "UNKNOWN"}
HEALTH_STATES = {"HEALTHY", "DEGRADED", "FAILED", "UNKNOWN"}
REGISTRATION_STATES = {"ACTIVE", "PAUSED", "REVIEW_REQUIRED", "PROHIBITED", "RETIRED"}
REVIEW_STATES = {"APPROVED", "REVIEW_REQUIRED", "PROHIBITED"}
PAGINATION_MODES = {"NONE", "OFFSET_LIMIT", "CURSOR", "PAGE", "LINK_HEADER", "SOURCE_SPECIFIC", "UNKNOWN"}
BACKOFF_MODES = {"BOUNDED_EXPONENTIAL", "BOUNDED_LINEAR", "NONE"}
REQUIRED = {
    "source_id", "provider", "source_tier", "authority_class", "jurisdiction", "source_type",
    "canonical_url", "authentication_mode", "cadence", "freshness_sla_hours", "native_id_strategy",
    "schema_fingerprint", "parser_version", "rights", "network_scope", "pagination", "retry_policy",
    "health", "provenance", "registration_state",
}


def _fail(message: str) -> None:
    raise ValueError(message)


def _validate_active_public_url(source_id: str, parsed: Any) -> None:
    if parsed.username is not None or parsed.password is not None:
        _fail(f"{source_id}: active source URL cannot embed credentials")
    hostname = str(parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        _fail(f"{source_id}: active source URL requires hostname")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        _fail(f"{source_id}: active source URL cannot target local hostnames")
    if hostname.isdigit():
        _fail(f"{source_id}: active source URL cannot use numeric hostname shorthand")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        _fail(f"{source_id}: active source URL IP must be globally routable")


def _validate_enum_fields(source_id: str, row: dict[str, Any]) -> None:
    checks = (
        ("source_tier", SOURCE_TIERS),
        ("source_type", SOURCE_TYPES),
        ("authority_class", AUTHORITY_CLASSES),
        ("authentication_mode", AUTH_MODES),
        ("network_scope", NETWORK_SCOPES),
        ("health", HEALTH_STATES),
        ("registration_state", REGISTRATION_STATES),
    )
    for field, allowed in checks:
        if row[field] not in allowed:
            _fail(f"{source_id}: invalid {field}")


def _validate_url(source_id: str, row: dict[str, Any], is_active: bool) -> None:
    parsed = urlparse(str(row["canonical_url"]))
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        _fail(f"{source_id}: canonical_url must be absolute HTTP(S)")
    if not is_active:
        return
    if parsed.scheme != "https":
        _fail(f"{source_id}: active automated source must use HTTPS")
    _validate_active_public_url(source_id, parsed)


def _validate_active_metadata(source_id: str, row: dict[str, Any], is_active: bool) -> None:
    if not is_active:
        return
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


def _validate_rights(source_id: str, row: dict[str, Any], is_active: bool) -> None:
    rights = row["rights"]
    if not isinstance(rights, dict):
        _fail(f"{source_id}: rights must be object")
    required = ("retrieval_allowed", "retention_allowed", "transformation_allowed", "public_projection_allowed", "attribution_required", "review_state")
    missing = [field for field in required if field not in rights]
    if missing:
        _fail(f"{source_id}: rights missing {missing[0]}")
    if rights["review_state"] not in REVIEW_STATES:
        _fail(f"{source_id}: invalid rights review_state")
    if not is_active:
        return
    if rights["review_state"] != "APPROVED" or rights["retrieval_allowed"] is not True:
        _fail(f"{source_id}: active source requires approved retrieval rights")
    if row["source_tier"] == "D" and rights["public_projection_allowed"] is True:
        _fail(f"{source_id}: Tier D source cannot independently allow public projection")


def _validate_pagination(source_id: str, row: dict[str, Any], is_active: bool) -> None:
    pagination = row["pagination"]
    if not isinstance(pagination, dict):
        _fail(f"{source_id}: pagination must be object")
    required = ("mode", "deterministic_ordering", "exhaustion_or_total_parity_required")
    missing = [field for field in required if field not in pagination]
    if missing:
        _fail(f"{source_id}: pagination missing {missing[0]}")
    if pagination["mode"] not in PAGINATION_MODES:
        _fail(f"{source_id}: invalid pagination mode")
    if not is_active:
        return
    if pagination["mode"] == "UNKNOWN":
        _fail(f"{source_id}: active source cannot have UNKNOWN pagination")
    paginated = pagination["mode"] != "NONE"
    if paginated and pagination["deterministic_ordering"] is not True:
        _fail(f"{source_id}: paginated source requires deterministic ordering")
    if paginated and pagination["exhaustion_or_total_parity_required"] is not True:
        _fail(f"{source_id}: paginated source requires exhaustion/total parity")


def _validate_retry_and_freshness(source_id: str, row: dict[str, Any]) -> None:
    retry = row["retry_policy"]
    if not isinstance(retry, dict):
        _fail(f"{source_id}: retry_policy must be object")
    required = ("max_attempts", "backoff", "retryable_status_classes")
    missing = [field for field in required if field not in retry]
    if missing:
        _fail(f"{source_id}: retry_policy missing {missing[0]}")
    if retry["backoff"] not in BACKOFF_MODES:
        _fail(f"{source_id}: invalid retry backoff")
    attempts = int(retry["max_attempts"])
    if attempts < 0 or attempts > 10:
        _fail(f"{source_id}: max_attempts must be between 0 and 10")
    if float(row["freshness_sla_hours"]) <= 0:
        _fail(f"{source_id}: freshness_sla_hours must be positive")


def _validate_row(index: int, row: Any, source_ids: set[str]) -> str:
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

    _validate_enum_fields(source_id, row)
    is_active = row["registration_state"] == "ACTIVE"
    _validate_url(source_id, row, is_active)
    _validate_active_metadata(source_id, row, is_active)
    _validate_rights(source_id, row, is_active)
    _validate_pagination(source_id, row, is_active)
    _validate_retry_and_freshness(source_id, row)
    return str(row["registration_state"])


def validate_registry(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract") != CONTRACT:
        _fail("Unsupported source registry contract")
    records = payload.get("records")
    if not isinstance(records, list):
        _fail("Source registry records must be a list")

    source_ids: set[str] = set()
    states: Counter[str] = Counter()
    for index, row in enumerate(records):
        states[_validate_row(index, row, source_ids)] += 1

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
    summary = validate_registry(read_workspace_json(args.registry))
    print(__import__("json").dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
