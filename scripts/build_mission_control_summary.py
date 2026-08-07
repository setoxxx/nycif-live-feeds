#!/usr/bin/env python3
"""Build the reader-safe Mission Control summary from already-certified evidence.

This module is projection-only. It does not recalculate event identity, location
truth, publication eligibility, ranking, verification, occurrence grouping, or
pin precision. It validates and copies safe aggregate fields into the same
reader-safe release package used by the public shadow release builder.
"""
from __future__ import annotations

import json
import re
from typing import Any

from build_public_runtime_artifacts import PublicArtifactError

SCHEMA = "nycif-mission-control-summary-v1"
PUBLIC_SOURCE_LABELS = ("Permitted Events", "Citywide Calendar", "Parks BigApps")
HEALTH_VALUES = {"FRESH", "STALE", "BLOCKED", "UNAVAILABLE"}
DATA_HEALTH_VALUES = {"READY", "DEGRADED", "BLOCKED", "UNAVAILABLE"}
STATUS_VALUES = {"PASS", "PENDING", "BLOCKED", "UNAVAILABLE"}

ALLOWED_OUTPUT_FIELDS = {
    "schema_version",
    "generated_at",
    "release_id",
    "release_sha",
    "current_pointer",
    "data_health",
    "sources",
    "daily_event_count",
    "new_event_count",
    "projector_status",
    "reconciliation_status",
    "silent_identity_loss",
    "unsupported_exact_pins",
    "duplicate_exact_occurrences",
    "daily_health",
    "anonymous_audit_status",
    "rollback_release",
}
REQUIRED_OUTPUT_FIELDS = {
    "schema_version",
    "generated_at",
    "release_id",
    "release_sha",
    "data_health",
    "sources",
    "projector_status",
    "reconciliation_status",
    "silent_identity_loss",
    "unsupported_exact_pins",
    "duplicate_exact_occurrences",
    "daily_health",
    "anonymous_audit_status",
}
SOURCE_FIELDS = {"label", "health", "last_success_age_seconds", "safe_event_count", "last_release_id"}
ALLOWED_EVIDENCE_FIELDS = (ALLOWED_OUTPUT_FIELDS - {"schema_version", "rollback_release"}) | {"certified"}

FORBIDDEN_TEXT = (
    "raw.githubusercontent.com",
    "github.com/",
    "localhost",
    "127.0.0.1",
    "private source",
    "private endpoint",
    "resolver internals",
    "ranking formula",
    "verification internals",
)
CREDENTIAL_RE = re.compile(r"(?:bearer\s+[a-z0-9._-]+|sk-[a-z0-9_-]{8,}|api[_-]?key\s*[:=]|access[_-]?token\s*[:=]|token\s*[:=])", re.I)


def _non_negative_int_or_none(name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PublicArtifactError(f"{name} must be a non-negative integer or null")
    return value


def _safe_pointer(name: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PublicArtifactError(f"{name} must be a string")
    lowered = value.lower()
    if "://" in value or "@" in value or any(token in lowered for token in ("github", "localhost", "token", "credential")):
        raise PublicArtifactError(f"{name} must be an opaque identifier or relative reader-safe path")
    return value


def _scan_forbidden(payload: Any) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    for token in FORBIDDEN_TEXT:
        if token in encoded:
            raise PublicArtifactError(f"Mission Control evidence contains forbidden text: {token}")
    if CREDENTIAL_RE.search(encoded):
        raise PublicArtifactError("Mission Control evidence contains credential-like text")


def _validate_evidence_shape(evidence: dict[str, Any]) -> None:
    if evidence.get("certified") is not True:
        raise PublicArtifactError("Mission Control evidence must be explicitly certified")
    extra = set(evidence) - ALLOWED_EVIDENCE_FIELDS
    if extra:
        raise PublicArtifactError(f"Mission Control evidence contains unexpected fields: {sorted(extra)}")
    _scan_forbidden(evidence)


def _normalize_sources(raw_sources: Any, release_id: str) -> list[dict[str, Any]]:
    if raw_sources is None:
        raw_sources = []
    if not isinstance(raw_sources, list):
        raise PublicArtifactError("sources must be a list")
    by_label: dict[str, dict[str, Any]] = {}
    for item in raw_sources:
        if not isinstance(item, dict):
            raise PublicArtifactError("each source summary must be an object")
        extra = set(item) - SOURCE_FIELDS
        if extra:
            raise PublicArtifactError(f"source summary contains unexpected fields: {sorted(extra)}")
        label = item.get("label")
        if label not in PUBLIC_SOURCE_LABELS:
            raise PublicArtifactError(f"unknown public source label: {label!r}")
        if label in by_label:
            raise PublicArtifactError(f"duplicate public source label: {label}")
        health = item.get("health", "UNAVAILABLE")
        if health not in HEALTH_VALUES:
            raise PublicArtifactError(f"invalid source health for {label}: {health}")
        by_label[label] = {
            "label": label,
            "health": health,
            "last_success_age_seconds": _non_negative_int_or_none(f"{label}.last_success_age_seconds", item.get("last_success_age_seconds")),
            "safe_event_count": _non_negative_int_or_none(f"{label}.safe_event_count", item.get("safe_event_count")),
            "last_release_id": item.get("last_release_id") if isinstance(item.get("last_release_id"), str) else release_id,
        }
    return [
        by_label.get(label, {
            "label": label,
            "health": "UNAVAILABLE",
            "last_success_age_seconds": None,
            "safe_event_count": None,
            "last_release_id": release_id,
        })
        for label in PUBLIC_SOURCE_LABELS
    ]


def build_summary(evidence: dict[str, Any], release_sha: str, rollback_release_sha: str | None = None) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise PublicArtifactError("Mission Control evidence must be a JSON object")
    _validate_evidence_shape(evidence)
    evidence_release_sha = str(evidence.get("release_sha") or "").strip().lower()
    if evidence_release_sha != release_sha:
        raise PublicArtifactError("Mission Control evidence release_sha must match the release package SHA")
    release_id = evidence.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise PublicArtifactError("release_id is required")
    generated_at = evidence.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise PublicArtifactError("generated_at is required")

    data_health = evidence.get("data_health", "UNAVAILABLE")
    daily_health = evidence.get("daily_health", "UNAVAILABLE")
    projector_status = evidence.get("projector_status", "UNAVAILABLE")
    reconciliation_status = evidence.get("reconciliation_status", "UNAVAILABLE")
    anonymous_audit_status = evidence.get("anonymous_audit_status", "UNAVAILABLE")
    if data_health not in DATA_HEALTH_VALUES:
        raise PublicArtifactError(f"invalid data_health: {data_health}")
    if daily_health not in DATA_HEALTH_VALUES:
        raise PublicArtifactError(f"invalid daily_health: {daily_health}")
    for name, value in (
        ("projector_status", projector_status),
        ("reconciliation_status", reconciliation_status),
        ("anonymous_audit_status", anonymous_audit_status),
    ):
        if value not in STATUS_VALUES:
            raise PublicArtifactError(f"invalid {name}: {value}")

    summary: dict[str, Any] = {
        "schema_version": SCHEMA,
        "generated_at": generated_at,
        "release_id": release_id,
        "release_sha": release_sha,
        "data_health": data_health,
        "sources": _normalize_sources(evidence.get("sources"), release_id),
        "daily_event_count": _non_negative_int_or_none("daily_event_count", evidence.get("daily_event_count")),
        "new_event_count": _non_negative_int_or_none("new_event_count", evidence.get("new_event_count")),
        "projector_status": projector_status,
        "reconciliation_status": reconciliation_status,
        "silent_identity_loss": _non_negative_int_or_none("silent_identity_loss", evidence.get("silent_identity_loss")),
        "unsupported_exact_pins": _non_negative_int_or_none("unsupported_exact_pins", evidence.get("unsupported_exact_pins")),
        "duplicate_exact_occurrences": _non_negative_int_or_none("duplicate_exact_occurrences", evidence.get("duplicate_exact_occurrences")),
        "daily_health": daily_health,
        "anonymous_audit_status": anonymous_audit_status,
    }
    current_pointer = _safe_pointer("current_pointer", evidence.get("current_pointer"))
    if current_pointer is not None:
        summary["current_pointer"] = current_pointer
    if rollback_release_sha:
        summary["rollback_release"] = rollback_release_sha
    validate_summary(summary, release_sha)
    return summary


def validate_summary(summary: dict[str, Any], release_sha: str) -> None:
    extra = set(summary) - ALLOWED_OUTPUT_FIELDS
    missing = REQUIRED_OUTPUT_FIELDS - set(summary)
    if extra or missing:
        raise PublicArtifactError(f"Mission Control summary schema mismatch extra={sorted(extra)} missing={sorted(missing)}")
    if summary.get("release_sha") != release_sha:
        raise PublicArtifactError("Mission Control summary release_sha mismatch")
    _scan_forbidden(summary)
    _normalize_sources(summary.get("sources"), str(summary.get("release_id") or ""))
    for name in ("daily_event_count", "new_event_count", "silent_identity_loss", "unsupported_exact_pins", "duplicate_exact_occurrences"):
        _non_negative_int_or_none(name, summary.get(name))
    _safe_pointer("current_pointer", summary.get("current_pointer"))
    _safe_pointer("rollback_release", summary.get("rollback_release"))


def loads_evidence(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublicArtifactError(f"malformed Mission Control evidence JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PublicArtifactError("Mission Control evidence must decode to an object")
    return payload
