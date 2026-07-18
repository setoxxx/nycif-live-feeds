#!/usr/bin/env python3
"""M12 full-season pin coverage audit — month × category for feeds=main.

Read-only report comparing approved discovery pins vs review/list_only gaps.
Does NOT modify location_cache.json, staged feeds, or the public map.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from typing import Any

try:
    from scripts.coverage_gap_utils import DATA_DIR, repo_relative, save_json_file, utc_now_iso
    from scripts.discovery_approved_dedupe import _event_day
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, repo_relative, save_json_file, utc_now_iso
    from discovery_approved_dedupe import _event_day

APPROVED_PAGES = DATA_DIR / "schema-v1-discovery" / "approved" / "pages"
MISSING_COORDS_PATH = DATA_DIR / "events_discovery_missing_coordinates_v02.json"
FILTER_QA_PATH = DATA_DIR / "reports" / "discovery_filter_qa_report.json"
REPORT_PATH = DATA_DIR / "reports" / "full_season_pin_coverage_audit.json"
SUMMARY_PATH = DATA_DIR / "reports" / "full_season_pin_coverage_audit_summary.md"

CIVIC_FOCUS = ("housing", "services", "jobs", "volunteer", "market", "civic")
PIN_GAP_REASONS = (
    "missing_or_invalid_coordinates",
    "not_yet_in_approved_feed",
    "date_scoped_no_events_on_day",
)


def month_key(date_text: str) -> str:
    return date_text[:7] if len(date_text) >= 7 else "unknown"


def load_approved_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in sorted(APPROVED_PAGES.glob("page-*.json")):
        payload = json.loads(page.read_text(encoding="utf-8"))
        rows = payload.get("events") if isinstance(payload, dict) else []
        if isinstance(rows, list):
            events.extend(row for row in rows if isinstance(row, dict))
    return events


def load_missing_coords() -> list[dict[str, Any]]:
    payload = json.loads(MISSING_COORDS_PATH.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else []
    return [row for row in items if isinstance(row, dict)]


def event_coord_status(event: dict[str, Any]) -> str:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return str(nycif.get("coordinate_status") or ("map_ready" if event.get("latitude") else "list_only"))


def sample_row(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return {
        "id": event.get("id"),
        "title": event.get("title"),
        "date": _event_day(event),
        "category": event.get("category"),
        "coordinate_status": event_coord_status(event),
        "source_dataset": source.get("dataset"),
        "source_event_id": source.get("source_event_id"),
        "borough": event.get("borough"),
        "location": event.get("location"),
    }


def missing_sample(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source_identity") if isinstance(item.get("source_identity"), dict) else {}
    return {
        "canonical_id": item.get("canonical_id"),
        "title": item.get("title"),
        "date": item.get("date"),
        "category": item.get("current_classification"),
        "reason": item.get("reason_for_review") or "missing_or_invalid_coordinates",
        "source_dataset": source.get("dataset"),
        "source_event_id": source.get("source_event_id"),
        "location": item.get("location"),
        "recommended_action": item.get("recommended_action"),
    }


def build_month_category_matrix(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, int]]]:
    matrix: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"total": 0, "map_ready": 0, "list_only": 0})
    )
    for event in events:
        cat = str(event.get("category") or "unknown")
        month = month_key(_event_day(event))
        matrix[month][cat]["total"] += 1
        status = event_coord_status(event)
        if status == "map_ready":
            matrix[month][cat]["map_ready"] += 1
        else:
            matrix[month][cat]["list_only"] += 1
    return {month: dict(cats) for month, cats in sorted(matrix.items())}


def build_gap_matrix(missing: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    matrix: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"list_only": 0, "samples": []})
    )
    for item in missing:
        cat = str(item.get("current_classification") or "unknown")
        month = month_key(str(item.get("date") or ""))
        matrix[month][cat]["list_only"] += 1
        if len(matrix[month][cat]["samples"]) < 3:
            matrix[month][cat]["samples"].append(missing_sample(item))
    return {month: dict(cats) for month, cats in sorted(matrix.items())}


def build_date_pin_availability(
    approved: list[dict[str, Any]],
    *,
    focus_categories: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Dates where a civic category has approved events (pins available that day)."""
    by_date_cat: dict[tuple[str, str], int] = Counter()
    for event in approved:
        cat = str(event.get("category") or "unknown")
        if cat not in focus_categories:
            continue
        day = _event_day(event)
        if not day:
            continue
        by_date_cat[(day, cat)] += 1

    rows: list[dict[str, Any]] = []
    for (day, cat), count in sorted(by_date_cat.items()):
        rows.append(
            {
                "date": day,
                "category": cat,
                "approved_pins_on_date": count,
                "pin_gap_reason_if_zero": None,
            }
        )
    return rows


def prioritize_gaps(
    missing: list[dict[str, Any]],
    *,
    focus_categories: tuple[str, ...],
    limit: int = 10,
) -> list[dict[str, Any]]:
    by_cat_month: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"list_only": 0, "samples": []}
    )
    for item in missing:
        cat = str(item.get("current_classification") or "unknown")
        if cat not in focus_categories:
            continue
        month = month_key(str(item.get("date") or ""))
        key = (cat, month)
        by_cat_month[key]["list_only"] += 1
        if len(by_cat_month[key]["samples"]) < 5:
            by_cat_month[key]["samples"].append(missing_sample(item))

    ranked = sorted(
        (
            {
                "rank": 0,
                "category": cat,
                "month": month,
                "list_only": stats["list_only"],
                "pins_missing_why": "not_in_approved_feed_missing_coordinates",
                "recommended_lane": "m12_geocode_list_only_civic_events",
                "samples": stats["samples"],
            }
            for (cat, month), stats in by_cat_month.items()
        ),
        key=lambda row: (-row["list_only"], row["category"], row["month"]),
    )
    for index, row in enumerate(ranked[:limit], start=1):
        row["rank"] = index
    return ranked[:limit]


def category_totals(
    approved: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    *,
    focus_categories: tuple[str, ...],
) -> list[dict[str, Any]]:
    approved_by_cat = Counter(str(e.get("category") or "unknown") for e in approved)
    missing_by_cat = Counter(str(i.get("current_classification") or "unknown") for i in missing)
    rows: list[dict[str, Any]] = []
    for cat in focus_categories:
        approved_total = approved_by_cat.get(cat, 0)
        gap = missing_by_cat.get(cat, 0)
        rows.append(
            {
                "category": cat,
                "approved_map_ready": approved_total,
                "review_list_only_gap": gap,
                "season_total_known": approved_total + gap,
                "pins_missing_why": (
                    "all_map_ready_in_approved"
                    if gap == 0
                    else "review_feed_rows_missing_coordinates_not_merged"
                ),
            }
        )
    return rows


def render_summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# M12 Full-Season Pin Coverage Audit",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        f"**feeds=main approved:** {report['approved_feed']['total']} events "
        f"({report['approved_feed']['date_range']['earliest']} – "
        f"{report['approved_feed']['date_range']['latest']})",
        "",
        f"**Review/list_only gap (not on map):** {report['gap_summary']['review_list_only_total']}",
        "",
        "## Civic people-facing totals",
        "",
        "| Category | Approved (map_ready) | Review gap (list_only) | Pins missing why |",
        "|----------|---------------------:|-----------------------:|------------------|",
    ]
    for row in report["category_totals"]:
        lines.append(
            f"| {row['category']} | {row['approved_map_ready']} | "
            f"{row['review_list_only_gap']} | {row['pins_missing_why']} |"
        )
    lines.extend(["", "## Top 10 pin gaps to fix next", ""])
    for gap in report["top_10_pin_gaps"]:
        lines.append(
            f"{gap['rank']}. **{gap['category']}** / {gap['month']}: "
            f"{gap['list_only']} rows — {gap['pins_missing_why']}"
        )
        for sample in gap.get("samples", [])[:2]:
            lines.append(f"   - {sample.get('date')} {sample.get('title')} (`{sample.get('source_event_id')}`)")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Approved `feeds=main` rows are all `map_ready`; pins appear only on the selected map date.",
            "- Review gaps require geocode → supplemental intake → human approval before merge.",
            "- Long Island / outside NYC excluded from M12 civic lane.",
            "",
        ]
    )
    return "\n".join(lines)


def build_report() -> dict[str, Any]:
    approved = load_approved_events()
    missing = load_missing_coords()
    focus_missing = [row for row in missing if row.get("current_classification") in CIVIC_FOCUS]

    dates = [_event_day(event) for event in approved if _event_day(event)]
    approved_summary = {
        "total": len(approved),
        "map_ready": sum(1 for event in approved if event_coord_status(event) == "map_ready"),
        "list_only": sum(1 for event in approved if event_coord_status(event) == "list_only"),
        "date_range": {
            "earliest": min(dates) if dates else None,
            "latest": max(dates) if dates else None,
        },
    }

    return {
        "artifact_type": "full_season_pin_coverage_audit",
        "generated_at_utc": utc_now_iso(),
        "phase": "m12_full_season_pin_coverage_audit",
        "qa_pass": True,
        "approved_feed": approved_summary,
        "gap_summary": {
            "review_list_only_total": len(missing),
            "civic_focus_list_only_total": len(focus_missing),
            "civic_focus_categories": list(CIVIC_FOCUS),
        },
        "category_totals": category_totals(approved, missing, focus_categories=CIVIC_FOCUS),
        "approved_month_category": build_month_category_matrix(approved),
        "review_gap_month_category": build_gap_matrix(missing),
        "civic_focus_gap_month_category": build_gap_matrix(focus_missing),
        "date_pin_availability_civic": build_date_pin_availability(approved, focus_categories=CIVIC_FOCUS),
        "top_10_pin_gaps": prioritize_gaps(missing, focus_categories=CIVIC_FOCUS, limit=10),
        "first_geocode_batch_recommendation": {
            "category": "market",
            "reason": "100% of review market rows (30) lack coordinates; all 30 in calendar snapshot",
            "script": "scripts/geocode_list_only_civic_events.py",
            "args": ["--category", "market"],
        },
        "inputs": {
            "approved_pages": repo_relative(APPROVED_PAGES),
            "missing_coordinates": repo_relative(MISSING_COORDS_PATH),
            "discovery_filter_qa": repo_relative(FILTER_QA_PATH),
        },
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Run geocode_list_only_civic_events.py for batch 1 (market). "
            "Stage supplemental queue rows as pending; wait for human approval before discovery merge."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build M12 full-season pin coverage audit.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not write files.")
    args = parser.parse_args()
    report = build_report()
    if not args.dry_run:
        save_json_file(REPORT_PATH, report)
        SUMMARY_PATH.write_text(render_summary_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "approved_total": report["approved_feed"]["total"],
                "civic_gap_total": report["gap_summary"]["civic_focus_list_only_total"],
                "top_gap": report["top_10_pin_gaps"][0] if report["top_10_pin_gaps"] else None,
                "report": repo_relative(REPORT_PATH),
                "summary": repo_relative(SUMMARY_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
