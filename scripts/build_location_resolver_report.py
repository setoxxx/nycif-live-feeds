#!/usr/bin/env python3
"""Run tiered location resolver across GPS review tail and write admin report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_resolver import NYCLocationResolver
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_location_resolver import NYCLocationResolver

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORT_PATH = DATA / "location_resolver_report.json"
UNRESOLVED_PATH = DATA / "location_resolver_unresolved_queue.json"
NEEDS_REVIEW_PATH = DATA / "gps_needs_review_events.json"
UNFILLED_PATH = DATA / "gps_review_geocoding_unfilled_review_queue.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def rows_from(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def main() -> int:
    resolver = NYCLocationResolver.load_default()
    unresolved: list[dict[str, Any]] = []
    tier_counts: Counter[str] = Counter()
    resolved_count = 0
    input_count = 0

    for source_path, key, location_field in (
        (NEEDS_REVIEW_PATH, "events", "display_location"),
        (UNFILLED_PATH, "review_queue", "display_location"),
    ):
        for row in rows_from(load_json(source_path, {}), key):
            input_count += 1
            display = row.get(location_field) or row.get("location") or row.get("event_location")
            borough = row.get("borough") or row.get("event_borough")
            result = resolver.resolve(display_location=str(display or ""), borough=str(borough or "") or None)
            tier_counts[result.tier] += 1
            if result.resolved:
                resolved_count += 1
            else:
                unresolved.append(
                    {
                        "source_artifact": str(source_path.relative_to(ROOT)),
                        "display_location": display,
                        "borough": borough,
                        "title": row.get("title") or row.get("event_name"),
                        "group_key": row.get("group_key"),
                        "confidence_reason": result.confidence_reason,
                        "manual_review_status": "pending",
                        "promotion_allowed": False,
                    }
                )

    if resolver._live_calls:
        resolver.save_geosearch_cache()

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at_utc": generated_at,
        "phase": "tiered_location_resolver_audit",
        "input_count": input_count,
        "resolved_count": resolved_count,
        "unresolved_count": len(unresolved),
        "tier_counts": dict(tier_counts),
        "resolver_tiers": [
            "tier_1_location_cache_key / tier_1_gazetteer_display",
            "tier_2_geosearch_cache / tier_2_geosearch_midpoint",
            "tier_3_nyc_geosearch_live (when NYCIF_ALLOW_LIVE_GEOSEARCH=yes)",
            "unresolved → admin review queue",
        ],
        "live_geosearch_calls": resolver._live_calls,
        "public_map_modified": False,
        "location_cache_modified": False,
        "promotion_allowed": False,
        "next_required_step": "Review location_resolver_unresolved_queue.json on admin dashboard.",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    with UNRESOLVED_PATH.open("w", encoding="utf-8") as handle:
        json.dump({"generated_at_utc": generated_at, "unresolved_queue": unresolved}, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
