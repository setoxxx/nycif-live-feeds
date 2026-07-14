#!/usr/bin/env python3
"""Category audit for schema-v1 projected events."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import (  # noqa: E402
    VALID_CATEGORIES,
    extract_events,
    write_repo_json,
)

LAYER_FILES = {
    "approved": "data/events_schema_v1_staged.json",
    "review": "data/events_schema_v1_supplemental_review.json",
    "major": "data/events_schema_v1_major.json",
}


def count_fallback_classified(events: list[dict]) -> int:
    return sum(
        1
        for e in events
        if str((e.get("nycif") or {}).get("classification_reason") or "").startswith("keyword_")
        or (e.get("nycif") or {}).get("classification_reason") == "fallback_general_no_documented_rule"
        or (e.get("nycif") or {}).get("classification_reason") == "fallback_general"
    )


def collect_category_samples(events: list[dict]) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        cat = e.get("category")
        if len(samples[cat]) < 3:
            samples[cat].append(
                {
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "raw_category": (e.get("nycif") or {}).get("raw_category"),
                    "classification_reason": (e.get("nycif") or {}).get("classification_reason"),
                    "event_type": (e.get("nycif") or {}).get("event_type"),
                }
            )
    return samples


def collect_general_remaining(events: list[dict]) -> list[dict]:
    general_remaining = []
    for e in events:
        if e.get("category") != "general":
            continue
        general_remaining.append(
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "raw_category": (e.get("nycif") or {}).get("raw_category"),
                "event_type": (e.get("nycif") or {}).get("event_type"),
                "event_agency": (e.get("nycif") or {}).get("event_agency"),
                "classification_reason": (e.get("nycif") or {}).get("classification_reason"),
                "why_still_general": (
                    "No documented specific category matched title, event_type, agency, "
                    "or raw categories after backend general refinement."
                ),
            }
        )
    return general_remaining


def load_layer_events(name: str) -> list[dict]:
    if name not in LAYER_FILES:
        raise ValueError(f"unknown layer: {name}")
    rel = LAYER_FILES[name]
    path = ROOT.joinpath(*rel.split("/"))
    if not path.is_relative_to(ROOT):
        raise ValueError("layer path escape blocked")
    return extract_events(json.loads(path.read_text(encoding="utf-8")))


def audit_layer(name: str) -> dict:
    events = load_layer_events(name)
    by_norm = Counter(e.get("category") for e in events)
    by_raw = Counter((e.get("nycif") or {}).get("raw_category") for e in events)
    by_reason = Counter((e.get("nycif") or {}).get("classification_reason") for e in events)
    samples = collect_category_samples(events)
    general_remaining = collect_general_remaining(events)

    return {
        "layer": name,
        "total": len(events),
        "normalized_category_counts": dict(by_norm.most_common()),
        "normalized_sum": sum(by_norm.values()),
        "sum_equals_total": sum(by_norm.values()) == len(events),
        "invalid_categories": [c for c in by_norm if c not in VALID_CATEGORIES],
        "source_category_counts": {str(k): v for k, v in by_raw.most_common(50)},
        "fallback_classified_count": count_fallback_classified(events),
        "general_count": by_norm.get("general", 0),
        "remaining_general_records": general_remaining,
        "sample_rows_by_category": {k: samples[k] for k in sorted(samples)},
        "classification_reason_distribution": dict(by_reason.most_common()),
        "precedence": [
            "valid specific backend category (not general)",
            "preserve raw_category",
            "event_type documented mapping",
            "keyword refinement when backend is general/missing",
            "general only when no documented rule fits",
        ],
    }


def main() -> int:
    report = {
        "approved": audit_layer("approved"),
        "review": audit_layer("review"),
    }
    major_path = ROOT.joinpath("data", "events_schema_v1_major.json")
    if major_path.exists():
        report["major"] = audit_layer("major")
    report["qa_pass"] = all(
        layer.get("sum_equals_total") and not layer.get("invalid_categories")
        for layer in report.values()
        if isinstance(layer, dict) and "total" in layer
    )
    write_repo_json("data/events_schema_v1_category_audit.json", report)
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "approved_general": report["approved"]["general_count"],
                "report": "data/events_schema_v1_category_audit.json",
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
