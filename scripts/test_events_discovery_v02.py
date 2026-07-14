#!/usr/bin/env python3
"""Tests for discovery taxonomy v02 handshake."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import classify_record, load_contract, match_recurring_registry  # noqa: E402


def fail(msg: str) -> None:
    raise AssertionError(msg)


def main() -> int:
    errors: list[str] = []
    contract = load_contract()
    inventory = json.loads((ROOT / "data" / "events_source_inventory_v02.json").read_text())
    audit = json.loads((ROOT / "data" / "events_discovery_taxonomy_v02_audit.json").read_text())
    recon = json.loads((ROOT / "data" / "events_discovery_reconciliation_v02.json").read_text())
    validation = json.loads((ROOT / "data" / "events_discovery_schema_validation_v02.json").read_text())
    approved = json.loads((ROOT / "data" / "events_discovery_v02_approved.json").read_text())

    if inventory.get("source_file_count", 0) < 10:
        errors.append("inventory too small")
    if not recon.get("reconciles"):
        errors.append("reconciliation failed")
    if not validation.get("qa_pass"):
        errors.append("schema validation failed")
    if not audit.get("qa_pass"):
        errors.append("taxonomy audit failed")

    claims = audit.get("accessibility_claims") or {}
    for key, ok in claims.items():
        if not ok:
            errors.append(f"accessibility claim failed: {key}")

    # Contract slug parity with audit categories
    for cat in (audit.get("primary_category_counts") or {}):
        if cat not in contract["categories"]:
            errors.append(f"unknown category in audit: {cat}")

    # Classification samples
    samples = [
        ({"title": "Shape Up NYC: Running Group", "category": "general"}, "fitness"),
        ({"title": "Colombian Day Parade", "category": "general", "event_type": "Parade"}, "civic"),
        ({"title": "Yoga class in the park", "category": "general"}, "fitness"),
        ({"title": "Painting workshop", "category": "general"}, "arts"),
        ({"title": "Hart Island Tour (North Island)", "category": "general"}, "tours"),
        ({"title": "Bowling Greens - Maintenance Day - Closed All Day", "category": "general"}, "parks"),
        ({"title": "FIFA Fan Festival", "category": "general"}, "sports"),
        ({"title": "Tenant resource fair", "category": "general"}, "housing"),
        ({"title": "City Job Fair", "category": "general"}, "jobs"),
    ]
    for row, expected in samples:
        got = classify_record(row)["category"]
        if got != expected:
            errors.append(f"classify {row.get('title')}: expected {expected} got {got}")

    # Interests include education for workshop while primary arts
    yoga = classify_record({"title": "Yoga class beginner session", "category": "general"})
    if yoga["category"] != "fitness" or "education" not in yoga["interests"]:
        errors.append("yoga class interests")

    role = classify_record(
        {"title": "FIFA World Cup Bus Operations", "category": "general"}
    )
    if role["event_role"] != "transportation_operation":
        errors.append("fifa bus role")

    maint = classify_record(
        {"title": "Bowling Greens - Maintenance Day - Closed All Day", "category": "parks"}
    )
    if maint["event_role"] != "maintenance_or_closure":
        errors.append("maintenance role")

    # Approved events have required fields
    for e in approved["events"][:200]:
        for key in (
            "id",
            "event_group_id",
            "title",
            "category",
            "interests",
            "tags",
            "event_role",
            "significance",
            "timezone",
            "source",
        ):
            if key not in e:
                errors.append(f"missing {key}")
                break
        nycif = e.get("nycif") or {}
        for key in (
            "coordinate_status",
            "display_disposition",
            "classification_version",
            "classification_reason",
            "classification_confidence",
        ):
            if key not in nycif:
                errors.append(f"missing nycif.{key}")
                break

    # Frontend mirror exists
    mirror = ROOT / "docs" / "field-desk-map-deploy" / "discovery-taxonomy-v02"
    for name in (
        "index.html",
        "app-discovery-taxonomy-v02.js",
        "event-feed-schema-v1.js",
        "public-map-defaults-v01.js",
        "service-worker.js",
        "README.md",
    ):
        if not (mirror / name).exists():
            errors.append(f"missing mirror file {name}")

    if (mirror / "index.html").exists():
        html = (mirror / "index.html").read_text(encoding="utf-8")
        for needle in ("Kids / family", "Classes / workshops", "Volunteer", "Explore More", "Parks / outdoors"):
            if needle not in html:
                errors.append(f"index missing {needle}")
        if 'data-cat="parade"' in html:
            errors.append("obsolete parade slug present")

    report = {"qa_pass": not errors, "errors": errors[:50]}
    (ROOT / "data" / "events_discovery_v02_test_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
