#!/usr/bin/env python3
"""Full audit of legacy feeds vs schema-v1 projections."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from schema_v1_common import (
    VALID_CATEGORIES,
    event_date_key,
    extract_events,
    today_nyc_approx,
    utc_now,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGED_LEGACY = DATA / "nycif_staged_live_events.json"
SUPP_LEGACY = DATA / "supplemental_events_staging_feed.json"
STAGED_SCHEMA = DATA / "events_schema_v1_staged.json"
SUPP_SCHEMA = DATA / "events_schema_v1_supplemental_review.json"
MAJOR_LEGACY = ROOT / "nycif_major_radar_map_events.json"
MAJOR_SCHEMA = DATA / "events_schema_v1_major.json"
OUT_JSON = DATA / "events_schema_v1_full_audit_report.json"
OUT_MD = ROOT / "docs" / "events-schema-v1-full-audit.md"


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iso_date(value: str | None):
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return None


def analyze_layer(name: str, legacy_rows: list, schema_events: list | None) -> dict:
    today = today_nyc_approx()
    end7 = today + timedelta(days=7)  # inclusive today..today+7 (= 8 calendar days window matching app)
    # Document: Next 7 days = today through today + 7 days (matching current Field Desk dayRange).

    titles_missing = sum(1 for r in legacy_rows if not (r.get("title") or r.get("name") or r.get("search_label")))
    dates = []
    invalid_dates = 0
    missing_dates = 0
    for r in legacy_rows:
        d = str(r.get("date") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            dates.append(d)
            continue
        start = str(r.get("start_date_time") or "")
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", start)
        if m:
            dates.append(m.group(1))
        elif start:
            invalid_dates += 1
        else:
            missing_dates += 1

    borough_missing = sum(
        1 for r in legacy_rows if not (r.get("borough") or r.get("event_borough"))
    )
    location_missing = sum(
        1
        for r in legacy_rows
        if not (r.get("location") or r.get("display_location") or r.get("address"))
    )
    source_id_missing = sum(
        1
        for r in legacy_rows
        if not (r.get("source_event_id") or (isinstance(r.get("source"), dict) and r["source"].get("source_event_id")))
    )

    schema = schema_events or []
    ids = [e.get("id") for e in schema]
    dup_ids = [i for i, c in Counter(ids).items() if c > 1]
    title_date_loc = Counter()
    for e in schema:
        key = (
            str(e.get("title") or "").strip().lower(),
            event_date_key(e) or "",
            str(e.get("location") or "").strip().lower(),
        )
        title_date_loc[key] += 1
    dup_tdl = sum(1 for _, c in title_date_loc.items() if c > 1)

    map_ready = sum(1 for e in schema if (e.get("nycif") or {}).get("coordinate_status") == "map_ready")
    list_only = sum(1 for e in schema if (e.get("nycif") or {}).get("coordinate_status") == "list_only")
    by_cat = Counter(e.get("category") for e in schema)
    by_raw = Counter((e.get("nycif") or {}).get("raw_category") for e in schema)
    by_dataset = Counter((e.get("source") or {}).get("dataset") for e in schema)
    by_borough = Counter(e.get("borough") for e in schema)
    by_date = Counter(event_date_key(e) for e in schema if event_date_key(e))

    schema_dates = [event_date_key(e) for e in schema if event_date_key(e)]
    today_s = today.isoformat()
    end7_s = end7.isoformat()
    today_count = sum(1 for d in schema_dates if d == today_s)
    next7_count = sum(1 for d in schema_dates if today_s <= d <= end7_s)
    upcoming_count = sum(1 for d in schema_dates if d >= today_s)

    rejected = []
    for e in schema:
        if (e.get("nycif") or {}).get("coordinate_status") != "map_ready":
            rejected.append(
                {
                    "id": e.get("id"),
                    "reason": "invalid_or_missing_nyc_coordinates",
                    "latitude": e.get("latitude"),
                    "longitude": e.get("longitude"),
                }
            )

    return {
        "layer": name,
        "legacy_input_count": len(legacy_rows),
        "schema_output_count": len(schema),
        "counts_match": len(legacy_rows) == len(schema),
        "map_ready_count": map_ready,
        "list_only_count": list_only,
        "missing_title_count": titles_missing,
        "missing_date_count": missing_dates,
        "invalid_date_count": invalid_dates,
        "missing_borough_count": borough_missing,
        "missing_location_count": location_missing,
        "missing_source_id_count": source_id_missing,
        "duplicate_stable_id_count": len(dup_ids),
        "duplicate_stable_ids_sample": dup_ids[:20],
        "duplicate_title_date_location_count": dup_tdl,
        "normalized_category_counts": dict(by_cat.most_common()),
        "raw_category_counts": {str(k): v for k, v in by_raw.most_common(40)},
        "source_dataset_counts": {str(k): v for k, v in by_dataset.most_common(40)},
        "borough_counts": {str(k): v for k, v in by_borough.most_common()},
        "event_date_counts_top": {str(k): v for k, v in by_date.most_common(20)},
        "earliest_date": min(schema_dates) if schema_dates else None,
        "latest_date": max(schema_dates) if schema_dates else None,
        "records_today": today_count,
        "records_next_7_days": next7_count,
        "records_all_upcoming": upcoming_count,
        "map_render_rejects": {
            "count": len(rejected),
            "reasons": {"invalid_or_missing_nyc_coordinates": len(rejected)},
            "sample": rejected[:15],
        },
        "invalid_normalized_categories": [
            c for c in by_cat if c not in VALID_CATEGORIES
        ],
        "category_sum_equals_total": sum(by_cat.values()) == len(schema),
    }


def analyze_major(legacy_major: list | None, schema_major: list | None) -> dict:
    today = today_nyc_approx()
    end7 = (today + timedelta(days=7)).isoformat()
    today_s = today.isoformat()

    def dates_of(rows):
        out = []
        for r in rows or []:
            d = str(r.get("date") or "")[:10]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                out.append(d)
                continue
            start = str(r.get("start_date_time") or "")
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", start)
            if m:
                out.append(m.group(1))
            else:
                dk = event_date_key(r)
                if dk:
                    out.append(dk)
        return out

    legacy_dates = dates_of(legacy_major)
    schema_dates = dates_of(schema_major)
    stale_legacy = sum(1 for d in legacy_dates if d < today_s)
    return {
        "legacy_major_count": len(legacy_major or []),
        "legacy_earliest": min(legacy_dates) if legacy_dates else None,
        "legacy_latest": max(legacy_dates) if legacy_dates else None,
        "legacy_past_count": stale_legacy,
        "legacy_upcoming_count": sum(1 for d in legacy_dates if d >= today_s),
        "legacy_today": sum(1 for d in legacy_dates if d == today_s),
        "legacy_next7": sum(1 for d in legacy_dates if today_s <= d <= end7),
        "schema_major_count": len(schema_major or []),
        "schema_earliest": min(schema_dates) if schema_dates else None,
        "schema_latest": max(schema_dates) if schema_dates else None,
        "schema_today": sum(1 for d in schema_dates if d == today_s),
        "schema_next7": sum(1 for d in schema_dates if today_s <= d <= end7),
        "schema_upcoming": sum(1 for d in schema_dates if d >= today_s),
        "legacy_is_stale": bool(legacy_dates) and (max(legacy_dates) < today_s or stale_legacy > len(legacy_dates) * 0.5),
    }


def main() -> int:
    staged_legacy = extract_events(load(STAGED_LEGACY) or {})
    supp_legacy = extract_events(load(SUPP_LEGACY) or {})
    staged_schema = extract_events(load(STAGED_SCHEMA) or {})
    supp_schema = extract_events(load(SUPP_SCHEMA) or {})
    major_legacy = extract_events(load(MAJOR_LEGACY) or [])
    major_schema = extract_events(load(MAJOR_SCHEMA) or {})

    approved = analyze_layer("approved_staged", staged_legacy, staged_schema)
    review = analyze_layer("review_supplemental", supp_legacy, supp_schema)
    major = analyze_major(major_legacy, major_schema)

    combined_map = approved["map_ready_count"] + review["map_ready_count"]
    combined_list = approved["list_only_count"] + review["list_only_count"]
    report = {
        "generated_at_utc": utc_now(),
        "reference_today_nyc": today_nyc_approx().isoformat(),
        "next_7_days_definition": "today through today + 7 days (inclusive), matching current Field Desk dayRange()",
        "approved": approved,
        "supplemental": review,
        "combined": {
            "total_accessible_records": approved["schema_output_count"] + review["schema_output_count"],
            "map_ready_count": combined_map,
            "list_only_count": combined_list,
        },
        "major": major,
        "qa": {
            "approved_counts_match": approved["counts_match"],
            "supplemental_counts_match": review["counts_match"],
            "no_duplicate_approved_ids": approved["duplicate_stable_id_count"] == 0,
            "no_duplicate_supplemental_ids": review["duplicate_stable_id_count"] == 0,
            "categories_valid_approved": not approved["invalid_normalized_categories"],
            "categories_valid_supplemental": not review["invalid_normalized_categories"],
            "legacy_major_feed_stale": major["legacy_is_stale"],
            "location_cache_modified": False,
            "promotion_allowed": False,
        },
    }
    report["qa"]["pass"] = all(
        [
            report["qa"]["approved_counts_match"],
            report["qa"]["supplemental_counts_match"],
            report["qa"]["no_duplicate_approved_ids"],
            report["qa"]["no_duplicate_supplemental_ids"],
            report["qa"]["categories_valid_approved"],
            report["qa"]["categories_valid_supplemental"],
            approved["category_sum_equals_total"],
            review["category_sum_equals_total"],
        ]
    )

    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(
        "\n".join(
            [
                "# Events schema v1 full audit",
                "",
                f"Generated: `{report['generated_at_utc']}`",
                f"Reference today (America/New_York): `{report['reference_today_nyc']}`",
                "",
                f"**QA pass:** `{report['qa']['pass']}`",
                "",
                "## Counts",
                "",
                f"- Approved legacy → schema: {approved['legacy_input_count']} → {approved['schema_output_count']}",
                f"- Supplemental legacy → schema: {review['legacy_input_count']} → {review['schema_output_count']}",
                f"- Combined accessible: {report['combined']['total_accessible_records']}",
                f"- Map-ready: {report['combined']['map_ready_count']}",
                f"- List-only: {report['combined']['list_only_count']}",
                "",
                "## Date windows (schema)",
                "",
                f"- Approved today / next7 / upcoming: {approved['records_today']} / {approved['records_next_7_days']} / {approved['records_all_upcoming']}",
                f"- Supplemental today / next7 / upcoming: {review['records_today']} / {review['records_next_7_days']} / {review['records_all_upcoming']}",
                "",
                "## Major feed",
                "",
                f"- Legacy major count: {major['legacy_major_count']} (past {major['legacy_past_count']}, upcoming {major['legacy_upcoming_count']})",
                f"- Legacy date range: {major['legacy_earliest']} → {major['legacy_latest']}",
                f"- Legacy stale: `{major['legacy_is_stale']}`",
                f"- Schema major count: {major['schema_major_count']} (today {major['schema_today']}, next7 {major['schema_next7']}, upcoming {major['schema_upcoming']})",
                "",
                "## Notes",
                "",
                "- Next 7 days = today through today+7 inclusive.",
                "- Records rejected from map rendering keep LIST ONLY access in the event list.",
                "- Supplemental records remain non-production / non-promoted.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"qa_pass": report["qa"]["pass"], "report": str(OUT_JSON)}, indent=2))
    return 0 if report["qa"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
