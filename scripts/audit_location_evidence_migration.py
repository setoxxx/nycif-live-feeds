#!/usr/bin/env python3
"""Read-only audit of location-evidence migration debt for official permit events.

This script deliberately does not promote, geocode, mutate caches, or write any
production feed. It classifies the current match selected by the existing
matching stack and separately reports:

* recovery candidates that deserve authoritative re-resolution; and
* rows already carrying publication-ready explicit evidence.

A recovery candidate is not a recovered pin.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

try:
    from scripts import build_test_enriched_feed as enrich
    from scripts.legacy_location_evidence_migration import migration_decision
    from scripts.location_evidence_contract import normalize_location_evidence
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import build_test_enriched_feed as enrich  # type: ignore[no-redef]
    from legacy_location_evidence_migration import migration_decision
    from location_evidence_contract import normalize_location_evidence


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def coordinate_pair(match: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(match, dict):
        return None
    lat = _finite(match.get("lat", match.get("latitude")))
    lng = _finite(match.get("lng", match.get("longitude")))
    if lat is None or lng is None:
        return None
    return lat, lng


def classification(match_type: str, match: dict[str, Any] | None) -> str:
    evidence = normalize_location_evidence(match_type, match)
    coords = coordinate_pair(match)
    exact = evidence.get("exact_pin_eligible") is True
    validated = str(evidence.get("validation_state") or "").lower() == "validated"
    tier = str(evidence.get("tier") or "")

    if exact and validated and coords is not None:
        return "READY_EXPLICIT_EVIDENCE"
    if coords is not None and tier == "legacy_match":
        return "MIGRATION_DEBT_LEGACY_COORDINATES"
    if coords is not None and tier == "exact_source_coordinate" and not (exact and validated):
        return "MIGRATION_DEBT_SOURCE_COORDINATES"
    if coords is not None and evidence.get("reason_code") == "NO_EXPLICIT_EXACT_LOCATION_EVIDENCE":
        return "MIGRATION_DEBT_COORDINATES_NO_ENVELOPE"
    if coords is not None:
        return "COORDINATES_REQUIRE_VALIDATION"
    if match_type == "none" or not isinstance(match, dict):
        return "UNRESOLVED_NO_MATCH"
    return "MATCH_WITHOUT_COORDINATES"


def audit_rows(
    raw_rows: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    cache: dict[str, Any],
    resolver: Any,
) -> dict[str, Any]:
    indexes = enrich.build_indexes(enriched)
    buckets: Counter[str] = Counter()
    match_counts: Counter[str] = Counter()
    recovery_reasons: Counter[str] = Counter()
    candidate_tiers: Counter[str] = Counter()
    eligible_tiers: Counter[str] = Counter()
    candidate_agencies: Counter[str] = Counter()
    by_match: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recovery_candidate_count = 0
    publication_eligible_count = 0

    for raw in raw_rows:
        match_type, match = enrich.find_match(raw, indexes, cache, resolver)
        bucket = classification(match_type, match)
        migration = migration_decision(raw, match_type, match)
        match_counts[match_type] += 1
        buckets[bucket] += 1
        by_match[match_type][bucket] += 1
        reason = str(migration.get("reason_code") or "UNSPECIFIED")
        recovery_reasons[reason] += 1

        if migration.get("candidate") is True:
            recovery_candidate_count += 1
            tier = str(migration.get("candidate_tier") or "UNSPECIFIED")
            candidate_tiers[tier] += 1
            agency = str(raw.get("event_agency") or "UNSPECIFIED").strip() or "UNSPECIFIED"
            candidate_agencies[agency] += 1

        if migration.get("eligible") is True:
            publication_eligible_count += 1
            eligible_tiers[str(migration.get("tier") or "UNSPECIFIED")] += 1

        if len(samples[bucket]) < 5:
            evidence = normalize_location_evidence(match_type, match)
            samples[bucket].append({
                "source_event_id": raw.get("event_id") or raw.get("source_event_id") or raw.get("id"),
                "title": raw.get("event_name") or raw.get("title") or raw.get("name"),
                "event_agency": raw.get("event_agency"),
                "event_location": raw.get("event_location") or raw.get("location"),
                "start_date_time": raw.get("start_date_time"),
                "match_type": match_type,
                "coordinate_pair_present": coordinate_pair(match) is not None,
                "evidence_tier": evidence.get("tier"),
                "validation_state": evidence.get("validation_state"),
                "exact_pin_eligible": evidence.get("exact_pin_eligible") is True,
                "source_provenance": evidence.get("source_provenance"),
                "reason_code": evidence.get("reason_code"),
                "recovery_candidate": migration.get("candidate") is True,
                "recovery_candidate_tier": migration.get("candidate_tier"),
                "recovery_reason": migration.get("reason_code"),
                "publication_eligible": migration.get("eligible") is True,
            })

    total = len(raw_rows)
    accounted = sum(buckets.values())
    migration_debt = sum(
        count for key, count in buckets.items() if key.startswith("MIGRATION_DEBT_")
    )
    return {
        "schema_version": "NYCIF_LOCATION_EVIDENCE_MIGRATION_AUDIT_V3",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "tvpp-9vvx",
        "read_only": True,
        "promotion_allowed": False,
        "input_rows": total,
        "accounted_rows": accounted,
        "silent_loss_count": total - accounted,
        "migration_debt_count": migration_debt,
        "recovery_candidate_count": recovery_candidate_count,
        "recovery_candidate_tier_counts": dict(sorted(candidate_tiers.items())),
        "recovery_candidate_agency_counts": dict(sorted(candidate_agencies.items())),
        "publication_eligible_count": publication_eligible_count,
        "publication_eligible_tier_counts": dict(sorted(eligible_tiers.items())),
        # Compatibility field retained so older dashboards fail safely instead
        # of interpreting candidates as recovered pins.
        "wave1_migration_eligible_count": publication_eligible_count,
        "wave1_migration_reason_counts": dict(sorted(recovery_reasons.items())),
        "wave1_migration_tier_counts": dict(sorted(eligible_tiers.items())),
        "bucket_counts": dict(sorted(buckets.items())),
        "match_counts": dict(sorted(match_counts.items())),
        "match_bucket_matrix": {
            key: dict(sorted(value.items())) for key, value in sorted(by_match.items())
        },
        "samples": dict(sorted(samples.items())),
    }


def build_audit() -> dict[str, Any]:
    raw_rows = enrich.fetch_raw_rows()
    raw_current = [
        row for row in raw_rows
        if enrich.date_key(row.get("start_date_time")) >= enrich.TODAY_NYC
    ]
    enriched = enrich.rows_from_payload(enrich.load_json_file(enrich.ENRICHED_PATH, []))
    cache = enrich.location_cache_entries()
    resolver = enrich.NYCLocationResolver.load_default()
    before_live_calls = resolver._live_calls
    report = audit_rows(raw_current, enriched, cache, resolver)
    if resolver._live_calls != before_live_calls:
        raise RuntimeError("read-only migration audit unexpectedly performed live geosearch")
    report["raw_rows_loaded"] = len(raw_rows)
    report["current_future_rows"] = len(raw_current)
    report["enriched_rows_loaded"] = len(enriched)
    report["location_cache_entries_loaded"] = len(cache)
    report["live_geosearch_calls"] = 0
    return report


def main() -> int:
    report = build_audit()
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    if report["silent_loss_count"] != 0:
        raise RuntimeError(f"location migration audit lost rows: {report['silent_loss_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
