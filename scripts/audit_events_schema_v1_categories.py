#!/usr/bin/env python3
"""Category audit for schema-v1 projected events."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import VALID_CATEGORIES, extract_events  # noqa: E402

OUT = ROOT / "data" / "events_schema_v1_category_audit.json"


def audit_layer(name: str, path: Path) -> dict:
    events = extract_events(json.loads(path.read_text(encoding="utf-8")))
    by_norm = Counter(e.get("category") for e in events)
    by_raw = Counter((e.get("nycif") or {}).get("raw_category") for e in events)
    by_reason = Counter((e.get("nycif") or {}).get("classification_reason") for e in events)
    fallback = sum(
        1
        for e in events
        if str((e.get("nycif") or {}).get("classification_reason") or "").startswith("keyword_")
        or (e.get("nycif") or {}).get("classification_reason") == "fallback_general"
    )
    general = by_norm.get("general", 0)
    samples = defaultdict(list)
    general_samples = []
    for e in events:
        cat = e.get("category")
        if len(samples[cat]) < 3:
            samples[cat].append(
                {
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "raw_category": (e.get("nycif") or {}).get("raw_category"),
                    "classification_reason": (e.get("nycif") or {}).get("classification_reason"),
                }
            )
        if cat == "general" and len(general_samples) < 15:
            general_samples.append(
                {
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "raw_category": (e.get("nycif") or {}).get("raw_category"),
                    "classification_reason": (e.get("nycif") or {}).get("classification_reason"),
                }
            )

    conflicts = []
    for e in events:
        raw = (e.get("nycif") or {}).get("raw_category")
        if raw and str(raw).lower() in VALID_CATEGORIES and e.get("category") != str(raw).lower():
            # parade historically maps to civic — not a conflict
            if str(raw).lower() == "parade" and e.get("category") == "civic":
                continue
            conflicts.append({"id": e.get("id"), "raw": raw, "normalized": e.get("category")})

    return {
        "layer": name,
        "total": len(events),
        "normalized_category_counts": dict(by_norm.most_common()),
        "normalized_sum": sum(by_norm.values()),
        "sum_equals_total": sum(by_norm.values()) == len(events),
        "invalid_categories": [c for c in by_norm if c not in VALID_CATEGORIES],
        "source_category_counts": {str(k): v for k, v in by_raw.most_common(50)},
        "fallback_classified_count": fallback,
        "general_count": general,
        "conflicting_category_count": len(conflicts),
        "conflicting_category_sample": conflicts[:20],
        "sample_rows_by_category": {k: samples[k] for k in sorted(samples)},
        "sample_rows_general": general_samples,
        "classification_reason_distribution": dict(by_reason.most_common()),
    }


def main() -> int:
    report = {
        "approved": audit_layer("approved", ROOT / "data" / "events_schema_v1_staged.json"),
        "review": audit_layer("review", ROOT / "data" / "events_schema_v1_supplemental_review.json"),
    }
    if (ROOT / "data" / "events_schema_v1_major.json").exists():
        report["major"] = audit_layer("major", ROOT / "data" / "events_schema_v1_major.json")
    report["qa_pass"] = all(
        layer.get("sum_equals_total") and not layer.get("invalid_categories")
        for layer in report.values()
        if isinstance(layer, dict) and "total" in layer
    )
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"qa_pass": report["qa_pass"], "report": str(OUT)}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
