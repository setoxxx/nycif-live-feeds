#!/usr/bin/env python3
"""QA report for discovery approved feed: categories, filters, duplicates."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from coverage_gap_utils import DATA_DIR, save_json_file, utc_now_iso  # noqa: E402
from discovery_approved_dedupe import _duplicate_group_key, _event_day, supplemental_fold_eligible  # noqa: E402

APPROVED_PAGES = DATA_DIR / "schema-v1-discovery" / "approved" / "pages"
REPORT_PATH = DATA_DIR / "reports" / "discovery_filter_qa_report.json"


def load_approved_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in sorted(APPROVED_PAGES.glob("page-*.json")):
        payload = json.loads(page.read_text(encoding="utf-8"))
        rows = payload.get("events") if isinstance(payload, dict) else []
        if isinstance(rows, list):
            events.extend(row for row in rows if isinstance(row, dict))
    return events


def build_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter()
    list_only_by_cat = Counter()
    pending_in_approved = 0
    duplicate_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    source_identity: set[tuple[str, str, str]] = set()
    source_dupes = 0
    ids: set[str] = set()
    duplicate_ids = 0

    for event in events:
        cat = str(event.get("category") or "unknown")
        categories[cat] += 1
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        if nycif.get("coordinate_status") == "list_only":
            list_only_by_cat[cat] += 1
        if str(nycif.get("manual_review_status") or "").lower() == "pending":
            pending_in_approved += 1
        eid = str(event.get("id") or "")
        if eid:
            if eid in ids:
                duplicate_ids += 1
            ids.add(eid)
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        identity = (
            str(source.get("dataset") or "").lower(),
            str(source.get("source_event_id") or ""),
            _event_day(event),
        )
        if identity in source_identity:
            source_dupes += 1
        source_identity.add(identity)
        key = _duplicate_group_key(event)
        if key:
            duplicate_groups[key].append(eid)

    cross_source_dupes = sum(len(v) - 1 for v in duplicate_groups.values() if len(v) > 1)
    errors: list[str] = []
    if duplicate_ids:
        errors.append(f"duplicate_ids={duplicate_ids}")
    if source_dupes:
        errors.append(f"source_identity_dupes={source_dupes}")
    if pending_in_approved:
        errors.append(f"pending_manual_review_in_approved={pending_in_approved}")

    return {
        "artifact_type": "discovery_filter_qa_report",
        "generated_at_utc": utc_now_iso(),
        "qa_pass": not errors,
        "errors": errors,
        "summary": {
            "approved_total": len(events),
            "category_counts": dict(categories),
            "list_only_by_category": dict(list_only_by_cat),
            "pending_in_approved": pending_in_approved,
            "cross_source_duplicate_rows": cross_source_dupes,
            "duplicate_id_rows": duplicate_ids,
            "source_identity_duplicate_rows": source_dupes,
        },
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
        },
    }


def main() -> int:
    report = build_report(load_approved_events())
    save_json_file(REPORT_PATH, report)
    print(json.dumps({"qa_pass": report["qa_pass"], "report": str(REPORT_PATH.relative_to(ROOT))}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
