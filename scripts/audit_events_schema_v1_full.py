#!/usr/bin/env python3
"""Full audit of legacy feeds vs schema-v1 projections."""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

from schema_v1_common import (
    ISO_DATE_PREFIX_RE,
    ISO_DATE_RE,
    VALID_CATEGORIES,
    event_date_key,
    extract_events,
    today_nyc_approx,
    utc_now,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_JSON = DATA / "events_schema_v1_full_audit_report.json"
OUT_MD = ROOT / "docs" / "events-schema-v1-full-audit.md"


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def collect_legacy_dates(legacy_rows: list) -> tuple[list[str], int, int]:
    dates = []
    invalid_dates = 0
    missing_dates = 0
    for row in legacy_rows:
        day = str(row.get("date") or "")[:10]
        if ISO_DATE_RE.fullmatch(day):
            dates.append(day)
            continue
        start = str(row.get("start_date_time") or "")
        match = ISO_DATE_PREFIX_RE.match(start)
        if match:
            dates.append(match.group(1))
        elif start:
            invalid_dates += 1
        else:
            missing_dates += 1
    return dates, invalid_dates, missing_dates


def schema_date_stats(schema_events: list) -> dict:
    today = today_nyc_approx()
    end7 = today + timedelta(days=7)
    today_s = today.isoformat()
    end7_s = end7.isoformat()
    schema_dates = [event_date_key(e) for e in schema_events if event_date_key(e)]
    return {
        "schema_dates": schema_dates,
        "records_today": sum(1 for d in schema_dates if d == today_s),
        "records_next_7_days": sum(1 for d in schema_dates if today_s <= d <= end7_s),
        "records_all_upcoming": sum(1 for d in schema_dates if d >= today_s),
        "earliest_date": min(schema_dates) if schema_dates else None,
        "latest_date": max(schema_dates) if schema_dates else None,
    }


def layer_missing_counts(legacy_rows: list) -> dict[str, int]:
    return {
        "missing_title_count": sum(
            1 for r in legacy_rows if not (r.get("title") or r.get("name") or r.get("search_label"))
        ),
        "missing_borough_count": sum(
            1 for r in legacy_rows if not (r.get("borough") or r.get("event_borough"))
        ),
        "missing_location_count": sum(
            1
            for r in legacy_rows
            if not (r.get("location") or r.get("display_location") or r.get("address"))
        ),
        "missing_source_id_count": sum(
            1
            for r in legacy_rows
            if not (
                r.get("source_event_id")
                or (isinstance(r.get("source"), dict) and r["source"].get("source_event_id"))
            )
        ),
    }


def layer_duplicate_stats(schema: list) -> dict:
    ids = [e.get("id") for e in schema]
    dup_ids = [i for i, c in Counter(ids).items() if c > 1]
    title_date_loc = Counter(
        (
            str(e.get("title") or "").strip().lower(),
            event_date_key(e) or "",
            str(e.get("location") or "").strip().lower(),
        )
        for e in schema
    )
    return {
        "duplicate_stable_id_count": len(dup_ids),
        "duplicate_stable_ids_sample": dup_ids[:20],
        "duplicate_title_date_location_count": sum(1 for _, c in title_date_loc.items() if c > 1),
    }


def layer_map_render_rejects(schema: list, list_only: list) -> dict:
    return {
        "count": len(list_only),
        "reasons": {"invalid_or_missing_nyc_coordinates": len(list_only)},
        "sample": [
            {
                "id": e.get("id"),
                "reason": "invalid_or_missing_nyc_coordinates",
                "latitude": e.get("latitude"),
                "longitude": e.get("longitude"),
            }
            for e in list_only[:15]
        ],
    }


def analyze_layer(name: str, legacy_rows: list, schema_events: list | None) -> dict:
    schema = schema_events or []
    _, invalid_dates, missing_dates = collect_legacy_dates(legacy_rows)
    by_cat = Counter(e.get("category") for e in schema)
    by_raw = Counter((e.get("nycif") or {}).get("raw_category") for e in schema)
    by_dataset = Counter((e.get("source") or {}).get("dataset") for e in schema)
    by_borough = Counter(e.get("borough") for e in schema)
    by_date = Counter(event_date_key(e) for e in schema if event_date_key(e))
    date_stats = schema_date_stats(schema)
    list_only = [
        e for e in schema if (e.get("nycif") or {}).get("coordinate_status") == "list_only"
    ]
    map_ready = len(schema) - len(list_only)
    missing = layer_missing_counts(legacy_rows)
    dupes = layer_duplicate_stats(schema)

    return {
        "layer": name,
        "legacy_input_count": len(legacy_rows),
        "schema_output_count": len(schema),
        "counts_match": len(legacy_rows) == len(schema),
        "map_ready_count": map_ready,
        "list_only_count": len(list_only),
        **missing,
        "missing_date_count": missing_dates,
        "invalid_date_count": invalid_dates,
        **dupes,
        "normalized_category_counts": dict(by_cat.most_common()),
        "raw_category_counts": {str(k): v for k, v in by_raw.most_common(40)},
        "source_dataset_counts": {str(k): v for k, v in by_dataset.most_common(40)},
        "borough_counts": {str(k): v for k, v in by_borough.most_common()},
        "event_date_counts_top": {str(k): v for k, v in by_date.most_common(20)},
        "earliest_date": date_stats["earliest_date"],
        "latest_date": date_stats["latest_date"],
        "records_today": date_stats["records_today"],
        "records_next_7_days": date_stats["records_next_7_days"],
        "records_all_upcoming": date_stats["records_all_upcoming"],
        "map_render_rejects": layer_map_render_rejects(schema, list_only),
        "invalid_normalized_categories": [c for c in by_cat if c not in VALID_CATEGORIES],
        "category_sum_equals_total": sum(by_cat.values()) == len(schema),
    }


def legacy_row_date(row) -> str | None:
    day = str(row.get("date") or "")[:10]
    if ISO_DATE_RE.fullmatch(day):
        return day
    start = str(row.get("start_date_time") or "")
    match = ISO_DATE_PREFIX_RE.match(start)
    if match:
        return match.group(1)
    return event_date_key(row)


def collect_major_dates(rows: list | None) -> list[str]:
    out = []
    for row in rows or []:
        key = legacy_row_date(row)
        if key:
            out.append(key)
    return out


def analyze_major(legacy_major: list | None, schema_major: list | None) -> dict:
    today_s = today_nyc_approx().isoformat()
    end7 = (today_nyc_approx() + timedelta(days=7)).isoformat()

    legacy_dates = collect_major_dates(legacy_major)
    schema_dates = collect_major_dates(schema_major)
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
        "legacy_is_stale": bool(legacy_dates)
        and (max(legacy_dates) < today_s or stale_legacy > len(legacy_dates) * 0.5),
    }


def write_markdown(report: dict) -> None:
    approved = report["approved"]
    review = report["supplemental"]
    major = report["major"]
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
                "## Major feed",
                "",
                f"- Legacy major count: {major['legacy_major_count']}",
                f"- Schema major count: {major['schema_major_count']} (today {major['schema_today']}, next7 {major['schema_next7']}, upcoming {major['schema_upcoming']})",
                "",
                "Next 7 days = today through today+7 inclusive.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    staged_legacy = extract_events(load(DATA / "nycif_staged_live_events.json") or {})
    supp_legacy = extract_events(load(DATA / "supplemental_events_staging_feed.json") or {})
    staged_schema = extract_events(load(DATA / "events_schema_v1_staged.json") or {})
    supp_schema = extract_events(load(DATA / "events_schema_v1_supplemental_review.json") or {})
    major_legacy = extract_events(load(ROOT / "nycif_major_radar_map_events.json") or [])
    major_schema = extract_events(load(DATA / "events_schema_v1_major.json") or {})

    approved = analyze_layer("approved_staged", staged_legacy, staged_schema)
    review = analyze_layer("review_supplemental", supp_legacy, supp_schema)
    major = analyze_major(major_legacy, major_schema)

    report = {
        "generated_at_utc": utc_now(),
        "reference_today_nyc": today_nyc_approx().isoformat(),
        "next_7_days_definition": "today through today + 7 days (inclusive)",
        "approved": approved,
        "supplemental": review,
        "combined": {
            "total_accessible_records": approved["schema_output_count"] + review["schema_output_count"],
            "map_ready_count": approved["map_ready_count"] + review["map_ready_count"],
            "list_only_count": approved["list_only_count"] + review["list_only_count"],
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
    write_markdown(report)
    print(json.dumps({"qa_pass": report["qa"]["pass"], "report": str(OUT_JSON)}, indent=2))
    return 0 if report["qa"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
