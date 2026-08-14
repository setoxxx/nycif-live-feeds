#!/usr/bin/env python3
"""Read-only audit of location-evidence migration debt for official permit events.

The audit keeps three disjoint states:
1. already publication-ready explicit evidence;
2. recovery candidates that still need authoritative re-resolution; and
3. any newly publication-eligible evidence produced by a migration validator.

Legacy/cache coordinates never become exact merely because they look plausible.
Recurring occurrences sharing the same borough/location/tier are collapsed into
one unique resolution claim for workload sizing.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

try:
    from scripts import build_test_enriched_feed as enrich
    from scripts.gps_identity import normalize_text_legacy
    from scripts.legacy_location_evidence_migration import migration_decision
    from scripts.location_evidence_contract import normalize_location_evidence
except ModuleNotFoundError:  # pragma: no cover
    import build_test_enriched_feed as enrich  # type: ignore[no-redef]
    from gps_identity import normalize_text_legacy
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


def _candidate_claim_key(raw: dict[str, Any], tier: str) -> str:
    borough = normalize_text_legacy(raw.get("event_borough") or raw.get("borough"))
    location = normalize_text_legacy(raw.get("event_location") or raw.get("location"))
    return f"{tier}|{borough}|{location}"


def audit_rows(raw_rows: list[dict[str, Any]], enriched: list[dict[str, Any]], cache: dict[str, Any], resolver: Any) -> dict[str, Any]:
    indexes = enrich.build_indexes(enriched)
    buckets: Counter[str] = Counter()
    match_counts: Counter[str] = Counter()
    recovery_reasons: Counter[str] = Counter()
    candidate_tiers: Counter[str] = Counter()
    eligible_tiers: Counter[str] = Counter()
    candidate_agencies: Counter[str] = Counter()
    candidate_claims: Counter[str] = Counter()
    claim_examples: dict[str, dict[str, Any]] = {}
    by_match: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recovery_candidate_count = 0
    migration_new_publication_eligible_count = 0
    already_ready_explicit_count = 0

    for raw in raw_rows:
        match_type, match = enrich.find_match(raw, indexes, cache, resolver)
        bucket = classification(match_type, match)
        match_counts[match_type] += 1
        buckets[bucket] += 1
        by_match[match_type][bucket] += 1

        if bucket == "READY_EXPLICIT_EVIDENCE":
            already_ready_explicit_count += 1
            migration = {
                "candidate": False,
                "eligible": False,
                "reason_code": "ALREADY_READY_EXPLICIT_EVIDENCE",
            }
        else:
            migration = migration_decision(raw, match_type, match)

        reason = str(migration.get("reason_code") or "UNSPECIFIED")
        recovery_reasons[reason] += 1

        if migration.get("candidate") is True:
            recovery_candidate_count += 1
            tier = str(migration.get("candidate_tier") or "UNSPECIFIED")
            candidate_tiers[tier] += 1
            agency = str(raw.get("event_agency") or "UNSPECIFIED").strip() or "UNSPECIFIED"
            candidate_agencies[agency] += 1
            claim_key = _candidate_claim_key(raw, tier)
            candidate_claims[claim_key] += 1
            claim_examples.setdefault(claim_key, {
                "candidate_tier": tier,
                "borough": raw.get("event_borough") or raw.get("borough"),
                "event_location": raw.get("event_location") or raw.get("location"),
                "event_agency": raw.get("event_agency"),
                "reason_code": migration.get("reason_code"),
                "facility_ids": migration.get("facility_ids") or [],
            })

        if migration.get("eligible") is True:
            migration_new_publication_eligible_count += 1
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
                "already_ready_explicit": bucket == "READY_EXPLICIT_EVIDENCE",
                "recovery_candidate": migration.get("candidate") is True,
                "recovery_candidate_tier": migration.get("candidate_tier"),
                "recovery_reason": migration.get("reason_code"),
                "new_publication_eligible_from_migration": migration.get("eligible") is True,
            })

    total = len(raw_rows)
    accounted = sum(buckets.values())
    migration_debt = sum(count for key, count in buckets.items() if key.startswith("MIGRATION_DEBT_"))
    unique_claims_by_tier = Counter(key.split("|", 1)[0] for key in candidate_claims)
    top_claims = []
    for claim_key, occurrence_count in candidate_claims.most_common(50):
        item = dict(claim_examples[claim_key])
        item["occurrence_count"] = occurrence_count
        top_claims.append(item)

    publication_ready_total = already_ready_explicit_count + migration_new_publication_eligible_count
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
        "already_ready_explicit_evidence_count": already_ready_explicit_count,
        "recovery_candidate_count": recovery_candidate_count,
        "recovery_candidate_tier_counts": dict(sorted(candidate_tiers.items())),
        "recovery_candidate_agency_counts": dict(sorted(candidate_agencies.items())),
        "unique_recovery_claim_count": len(candidate_claims),
        "unique_recovery_claim_tier_counts": dict(sorted(unique_claims_by_tier.items())),
        "top_recovery_claims": top_claims,
        "migration_new_publication_eligible_count": migration_new_publication_eligible_count,
        "publication_ready_total_count": publication_ready_total,
        "publication_eligible_count": migration_new_publication_eligible_count,
        "publication_eligible_tier_counts": dict(sorted(eligible_tiers.items())),
        "wave1_migration_eligible_count": migration_new_publication_eligible_count,
        "wave1_migration_reason_counts": dict(sorted(recovery_reasons.items())),
        "wave1_migration_tier_counts": dict(sorted(eligible_tiers.items())),
        "bucket_counts": dict(sorted(buckets.items())),
        "match_counts": dict(sorted(match_counts.items())),
        "match_bucket_matrix": {key: dict(sorted(value.items())) for key, value in sorted(by_match.items())},
        "samples": dict(sorted(samples.items())),
    }


def build_audit() -> dict[str, Any]:
    raw_rows = enrich.fetch_raw_rows()
    raw_current = [row for row in raw_rows if enrich.date_key(row.get("start_date_time")) >= enrich.TODAY_NYC]
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
