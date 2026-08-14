#!/usr/bin/env python3
"""Read-only audit for authoritative recovery of TVPP street-segment locations.

The audit deduplicates current/future `MAIN between CROSS1 and CROSS2` claims,
then asks the canonical resolver for exact segment authority. It never saves the
Geoclient cache, never mutates production feeds, and never treats legacy
coordinates as evidence. A successful row requires either an explicit certified
segment reference or two borough-valid NYC Geoclient intersection endpoints.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_clock import nyc_today_iso
    from scripts.nyc_location_resolver import NYCLocationResolver, parse_street_between
    from scripts.sync_nyc_open_data import date_key, fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_clock import nyc_today_iso
    from nyc_location_resolver import NYCLocationResolver, parse_street_between
    from sync_nyc_open_data import date_key, fetch_raw_rows


def claim_key(row: dict[str, Any]) -> str:
    borough = normalize_text_legacy(row.get("event_borough") or row.get("borough"))
    location = normalize_text_legacy(row.get("event_location") or row.get("location"))
    return f"{borough}|{location}"


def current_segment_claims(rows: list[dict[str, Any]], today_nyc: str) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for row in rows:
        if date_key(row.get("start_date_time")) < today_nyc:
            continue
        location = str(row.get("event_location") or row.get("location") or "").strip()
        borough = str(row.get("event_borough") or row.get("borough") or "").strip()
        if not borough or not parse_street_between(location):
            continue
        key = claim_key(row)
        if key not in claims:
            claims[key] = {
                "borough": borough,
                "event_location": location,
                "occurrence_count": 0,
                "source_event_ids": [],
            }
        claims[key]["occurrence_count"] += 1
        source_id = str(row.get("event_id") or row.get("source_event_id") or "").strip()
        if source_id and len(claims[key]["source_event_ids"]) < 20:
            claims[key]["source_event_ids"].append(source_id)
    return claims


def audit_claims(
    claims: dict[str, dict[str, Any]],
    resolver: Any,
    *,
    credentials_available: bool,
    max_claims: int = 5000,
) -> dict[str, Any]:
    if len(claims) > max_claims:
        raise RuntimeError(f"unique street-segment claim count exceeds safety cap: {len(claims)} > {max_claims}")

    results: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    exact_count = 0

    for key in sorted(claims):
        claim = claims[key]
        result = resolver.resolve(
            display_location=claim["event_location"],
            borough=claim["borough"],
            cache_keys=[],
        )
        exact = (
            result.resolved is True
            and result.tier == "certified_street_segment"
            and result.validation_state == "validated"
            and result.exact_pin_eligible is True
            and result.lat is not None
            and result.lng is not None
        )
        reason = str(result.reason_code or "UNSPECIFIED")
        source = str(result.source or "UNRESOLVED")
        reason_counts[reason] += 1
        source_counts[source] += 1
        if exact:
            exact_count += 1
        results.append(
            {
                **claim,
                "claim_key": key,
                "exact_segment_certified": exact,
                "tier": result.tier,
                "latitude": result.lat if exact else None,
                "longitude": result.lng if exact else None,
                "source": source,
                "reason_code": reason,
                "validation_state": result.validation_state,
                "exact_pin_eligible": result.exact_pin_eligible is True,
                "query_used": result.query_used,
            }
        )

    geoclient = getattr(resolver, "geoclient", None)
    live_calls = int(getattr(geoclient, "live_calls", 0) or 0)
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_GEOCLIENT_RECOVERY_AUDIT_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "credentials_available": credentials_available,
        "unique_segment_claim_count": len(claims),
        "certified_segment_claim_count": exact_count,
        "unresolved_segment_claim_count": len(claims) - exact_count,
        "geoclient_live_call_count": live_calls,
        "reason_counts": dict(sorted(reason_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "claims": results,
    }


def build_report(max_claims: int = 5000) -> dict[str, Any]:
    rows = fetch_raw_rows()
    today_nyc = nyc_today_iso()
    claims = current_segment_claims(rows, today_nyc)
    credentials_available = bool(
        os.environ.get("NYC_GEOCLIENT_APP_ID", "").strip()
        and os.environ.get("NYC_GEOCLIENT_APP_KEY", "").strip()
    )
    resolver = NYCLocationResolver.load_default()
    report = audit_claims(
        claims,
        resolver,
        credentials_available=credentials_available,
        max_claims=max_claims,
    )
    report["raw_rows_loaded"] = len(rows)
    report["today_nyc"] = today_nyc
    report["live_geosearch_allowed"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-claims", type=int, default=5000)
    args = parser.parse_args()

    report = build_report(max_claims=args.max_claims)
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({
        key: report[key]
        for key in (
            "schema_version",
            "credentials_available",
            "raw_rows_loaded",
            "unique_segment_claim_count",
            "certified_segment_claim_count",
            "unresolved_segment_claim_count",
            "geoclient_live_call_count",
            "reason_counts",
            "source_counts",
        )
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
