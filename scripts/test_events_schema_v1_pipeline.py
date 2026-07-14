#!/usr/bin/env python3
"""Automated QA for schema-v1 + major pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import VALID_CATEGORIES, event_date_key, extract_events, today_nyc_approx  # noqa: E402

PROTECTED = [
    ROOT / "data" / "location_cache.json",
]

CATEGORY_SAMPLES = [
    ({"title": "Brownsville Old Timer's Parade", "category": "general", "event_type": "Parade"}, "civic"),
    ({"title": "Community March", "category": "general", "event_type": "Street Event"}, "civic"),
    ({"title": "15th Annual Trans Latina March", "category": "general"}, "civic"),
    ({"title": "July Falun Dafa Parade", "category": "general", "event_type": "Parade"}, "civic"),
    ({"title": "Colombian Day Parade", "category": "general", "event_type": "Parade"}, "civic"),
    ({"title": "Bayside 5K", "category": "general", "event_type": "Athletic Race / Tour"}, "sports"),
    ({"title": "Bedstuy HERITAGE 5k", "category": "general"}, "sports"),
    ({"title": "Unity Walk", "category": "general"}, "civic"),
    ({"title": "BARAAT PROCESSION", "category": "general"}, "civic"),
    ({"title": "Public Hearing on Budget", "category": "general"}, "government"),
    ({"title": "City Job Fair", "category": "general"}, "jobs"),
    ({"title": "Tenant Resource Event", "category": "general"}, "housing"),
    ({"title": "Sport - Youth Basketball", "category": "general", "event_type": "Sport - Youth"}, "sports"),
    ({"title": "Yoga and Zumba Wellness", "category": "general"}, "fitness"),
    ({"title": "Specific Sports Already", "category": "sports"}, "sports"),
]


def fail(msg: str) -> None:
    raise AssertionError(msg)


def check_envelopes(errors: list[str], staged: dict, supp: dict, major: dict) -> None:
    for label, env in (("staged", staged), ("supp", supp), ("major", major)):
        if env.get("schema_version") != "1.0":
            errors.append(f"{label} schema_version")
        if "generated_at_utc" not in env or "total" not in env or "next_cursor" not in env or "events" not in env:
            errors.append(f"{label} envelope fields")
        if env["total"] != len(env["events"]):
            errors.append(f"{label} total mismatch")


def check_input_counts(errors: list[str], staged: dict, supp: dict, staged_legacy: list, supp_legacy: list) -> None:
    if len(staged["events"]) != len(staged_legacy):
        errors.append("approved count mismatch")
    if len(supp["events"]) != len(supp_legacy):
        errors.append("supplemental count mismatch")


def check_event_fields(errors: list[str], staged: dict, major: dict) -> None:
    for e in staged["events"][:200] + major["events"][:200]:
        for key in ("id", "title", "category", "timezone", "latitude", "longitude", "significance", "source"):
            if key not in e:
                errors.append(f"missing {key}")
                break
        if e["category"] not in VALID_CATEGORIES:
            errors.append(f"bad category {e['category']}")
        if not isinstance(e.get("source"), dict):
            errors.append("bad source")
        if "lat" in e or "lng" in e:
            errors.append("legacy lat/lng")


def check_id_uniqueness(errors: list[str], staged: dict, supp: dict) -> None:
    ids = [e["id"] for e in staged["events"] + supp["events"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids across layers or within")


def check_supplemental_safety(errors: list[str], supp: dict) -> None:
    for e in supp["events"]:
        nycif = e.get("nycif") or {}
        if nycif.get("promotion_allowed") is True or nycif.get("production_feed") is True:
            errors.append("supplemental promotion/production")
        if e.get("significance") == "major":
            errors.append("supplemental marked major")
        if (nycif.get("coordinate_status") == "list_only") != (e.get("latitude") is None):
            errors.append("list-only coord mismatch")


def check_major_upcoming(errors: list[str], major: dict) -> None:
    today = today_nyc_approx().isoformat()
    major_upcoming = [e for e in major["events"] if (event_date_key(e) or "") >= today]
    if not major_upcoming:
        errors.append("major feed has no upcoming rows")


def check_report_artifacts(
    errors: list[str],
    validation: dict,
    major_report: dict,
    cat_audit: dict,
    full_audit: dict,
) -> None:
    if not validation.get("qa_pass"):
        errors.append("validation report failed")
    if not major_report.get("qa_pass"):
        errors.append("major report failed")
    if not cat_audit.get("qa_pass"):
        errors.append("category audit failed")
    if not full_audit.get("qa", {}).get("pass"):
        errors.append("full audit failed")


def check_protected_files(errors: list[str]) -> None:
    for p in PROTECTED:
        if not p.exists():
            errors.append(f"missing protected {p}")


def check_page_artifacts(errors: list[str]) -> None:
    if not (ROOT / "data" / "schema-v1" / "approved" / "manifest.json").exists():
        errors.append("missing approved manifest")
    if not (ROOT / "data" / "schema-v1" / "major" / "events.json").exists():
        errors.append("missing major events.json")


def check_category_samples(errors: list[str]) -> None:
    from schema_v1_common import infer_category  # noqa: E402

    for row, expected in CATEGORY_SAMPLES:
        got, _reason = infer_category(row, prefer_direct=True)
        if got != expected:
            errors.append(f"category sample {row.get('title')!r}: expected {expected}, got {got}")


def check_legacy_carryover_report(errors: list[str], major_report: dict) -> None:
    if major_report.get("legacy_carryover_only_count") is None:
        errors.append("major report missing legacy_carryover_only_count")
    samples_legacy = major_report.get("legacy_carryover_only_samples") or []
    if major_report.get("legacy_carryover_only_count", 0) >= 25 and len(samples_legacy) < 25:
        errors.append("major report needs >=25 legacy-only samples when count>=25")


def check_general_remaining(errors: list[str], cat_audit: dict) -> None:
    approved_general = (cat_audit.get("approved") or {}).get("remaining_general_records") or []
    for row in approved_general:
        if not row.get("why_still_general"):
            errors.append("general remaining row missing why_still_general")
            break


def main() -> int:
    errors: list[str] = []
    staged_legacy = extract_events(json.loads((ROOT / "data" / "nycif_staged_live_events.json").read_text()))
    supp_legacy = extract_events(json.loads((ROOT / "data" / "supplemental_events_staging_feed.json").read_text()))
    staged = json.loads((ROOT / "data" / "events_schema_v1_staged.json").read_text())
    supp = json.loads((ROOT / "data" / "events_schema_v1_supplemental_review.json").read_text())
    major = json.loads((ROOT / "data" / "events_schema_v1_major.json").read_text())
    validation = json.loads((ROOT / "data" / "events_schema_v1_validation_report.json").read_text())
    major_report = json.loads((ROOT / "data" / "events_schema_v1_major_report.json").read_text())
    cat_audit = json.loads((ROOT / "data" / "events_schema_v1_category_audit.json").read_text())
    full_audit = json.loads((ROOT / "data" / "events_schema_v1_full_audit_report.json").read_text())

    check_envelopes(errors, staged, supp, major)
    check_input_counts(errors, staged, supp, staged_legacy, supp_legacy)
    check_event_fields(errors, staged, major)
    check_id_uniqueness(errors, staged, supp)
    check_supplemental_safety(errors, supp)
    check_major_upcoming(errors, major)
    check_report_artifacts(errors, validation, major_report, cat_audit, full_audit)
    check_protected_files(errors)
    check_page_artifacts(errors)
    check_category_samples(errors)
    check_legacy_carryover_report(errors, major_report)
    check_general_remaining(errors, cat_audit)

    report = {"qa_pass": not errors, "errors": errors}
    (ROOT / "data" / "events_schema_v1_pipeline_test_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
