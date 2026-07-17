#!/usr/bin/env python3
"""Build supplemental location resolution engine disposition report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data" / "supplemental_manual_approval_queue.json"
REPORT_PATH = ROOT / "data" / "supplemental_location_resolution_engine_report.json"


def main() -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    rows = queue.get("approval_queue") or queue.get("rows") or []
    status_counts = Counter((r.get("manual_review_status") or "unknown") for r in rows)
    source_counts = Counter(
        (r.get("geocoder_source") or "none")
        for r in rows
        if (r.get("manual_review_status") or "") == "approved"
    )
    reject_reasons = Counter(
        (r.get("approval_decision_reason") or "unknown")[:80]
        for r in rows
        if (r.get("manual_review_status") or "") == "rejected"
    )
    approved = status_counts.get("approved", 0)
    rejected = status_counts.get("rejected", 0)
    pending = status_counts.get("pending", 0)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "queue_path": str(QUEUE_PATH.relative_to(ROOT)),
        "total_rows": len(rows),
        "approved_count": approved,
        "rejected_count": rejected,
        "pending_count": pending,
        "disposition_complete": pending == 0 and len(rows) > 0,
        "status_counts": dict(status_counts),
        "approved_geocoder_sources": dict(source_counts.most_common(30)),
        "top_reject_reasons": dict(reject_reasons.most_common(25)),
        "engine_tiers": [
            "parks_overlap",
            "child_in_parent_gazetteer",
            "full_display_gazetteer",
            "geoclient_intersection",
            "geoclient_intersection_in_parent",
            "calendar_parks_overlap",
            "nyc_location_resolver",
            "park_polygon_correction",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Disposition complete: {report['disposition_complete']}")


if __name__ == "__main__":
    main()
