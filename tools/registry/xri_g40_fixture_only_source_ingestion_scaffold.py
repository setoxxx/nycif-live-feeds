"""XRI-G40 fixture-only source ingestion scaffold.

This module is intentionally non-production and fixture-only. It performs no
network access, no geocoding, no registry writes, no public map output, and no
WordPress or scheduled workflow integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class FixtureOnlyScaffoldError(ValueError):
    """Raised when fixture-only safety rules fail closed."""


_FORBIDDEN_FLAG_FIELDS = {
    "live_url",
    "source_url",
    "api_url",
    "soda_endpoint",
    "nyc_open_data_endpoint",
    "requires_geocoding",
    "registry_write",
    "registry_import",
    "approval",
    "promotion",
    "publishing",
    "public_map_runtime",
    "public_map_output",
    "wordpress_output",
    "scheduled_workflow",
    "location_cache_access",
    "production_target",
}

_STABLE_IDENTITY_FIELDS = ("group_key", "display_location", "candidate_identity")


@dataclass(frozen=True)
class FixtureRecord:
    """Deterministic normalized representation of a fixture-only record."""

    group_key: str
    display_location: str
    candidate_identity: str
    display: Mapping[str, Any]


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)


def _reject_forbidden_fields(payload: Mapping[str, Any]) -> None:
    present = sorted(field for field in _FORBIDDEN_FLAG_FIELDS if _truthy(payload.get(field)))
    if present:
        raise FixtureOnlyScaffoldError(
            "Fixture-only scaffold rejected forbidden live/production fields: " + ", ".join(present)
        )

    for value in payload.values():
        if isinstance(value, str):
            lowered = value.lower()
            if "http://" in lowered or "https://" in lowered:
                raise FixtureOnlyScaffoldError("Fixture-only scaffold rejects live URLs")
            if "data.cityofnewyork.us" in lowered or "socrata" in lowered or "/resource/" in lowered:
                raise FixtureOnlyScaffoldError("Fixture-only scaffold rejects SODA/API/NYC Open Data targets")


def normalize_fixture_record(payload: Mapping[str, Any]) -> FixtureRecord:
    """Normalize one explicit fixture payload.

    The function fails closed unless all stable identity fields are present. The
    optional review_rank value is preserved only as display metadata and is never
    used as identity.
    """

    if not isinstance(payload, Mapping):
        raise FixtureOnlyScaffoldError("Fixture payload must be a mapping")

    _reject_forbidden_fields(payload)

    missing = [field for field in _STABLE_IDENTITY_FIELDS if not str(payload.get(field, "")).strip()]
    if missing:
        raise FixtureOnlyScaffoldError("Missing stable identity fields: " + ", ".join(missing))

    display = {
        key: payload[key]
        for key in sorted(payload)
        if key not in _STABLE_IDENTITY_FIELDS and key not in _FORBIDDEN_FLAG_FIELDS
    }
    if "review_rank" in display:
        display["review_rank_identity_use"] = "forbidden_display_only"

    return FixtureRecord(
        group_key=str(payload["group_key"]).strip(),
        display_location=str(payload["display_location"]).strip(),
        candidate_identity=str(payload["candidate_identity"]).strip(),
        display=display,
    )


def normalize_fixture_records(payloads: list[Mapping[str, Any]]) -> list[FixtureRecord]:
    """Normalize fixture payloads deterministically in input order."""

    if not isinstance(payloads, list):
        raise FixtureOnlyScaffoldError("Fixture payloads must be supplied as a list")
    return [normalize_fixture_record(payload) for payload in payloads]
