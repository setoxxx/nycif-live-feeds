#!/usr/bin/env python3
"""Inventory every event-like source block for discovery taxonomy v02."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import dump_md, extract_rows, write_json  # noqa: E402

# Explicit catalog — status is intentional, not inferred from filename alone.
SOURCE_CATALOG = [
    {
        "dataset_key": "raw-nyc-open-data-street-events",
        "file_path": "data/raw_nyc_open_data_snapshot.json",
        "current_pipeline_status": "used",
        "canonical_projection_status": "complete",
        "notes": ["Upstream NYC Open Data street/park event permits feeding staged projection."],
    },
    {
        "dataset_key": "nyc-citywide-events-calendar",
        "file_path": "data/nyc_citywide_events_calendar_snapshot.json",
        "current_pipeline_status": "review_only",
        "canonical_projection_status": "partial",
        "notes": ["Feeds supplemental review; some calendar rows may remain unlinked."],
    },
    {
        "dataset_key": "nyc-parks-bigapps-events",
        "file_path": "data/nyc_parks_bigapps_events_snapshot.json",
        "current_pipeline_status": "review_only",
        "canonical_projection_status": "partial",
        "notes": ["Parks events feed; subset present in supplemental."],
    },
    {
        "dataset_key": "nycif-staged-live-events",
        "file_path": "data/nycif_staged_live_events.json",
        "current_pipeline_status": "used",
        "canonical_projection_status": "complete",
        "notes": ["Approved production staged events after GPS disposition."],
    },
    {
        "dataset_key": "supplemental-events-staging-feed",
        "file_path": "data/supplemental_events_staging_feed.json",
        "current_pipeline_status": "review_only",
        "canonical_projection_status": "complete",
        "notes": ["Calendar + Parks review supplemental layer; promotion_allowed false."],
    },
    {
        "dataset_key": "nycif-all-radar-map-events",
        "file_path": "nycif_all_radar_map_events.json",
        "current_pipeline_status": "duplicative_source",
        "canonical_projection_status": "complete",
        "notes": ["Near-duplicate of staged with tiny delta; not counted as independent raw intake."],
    },
    {
        "dataset_key": "nycif-live-test-enriched-events",
        "file_path": "data/nycif_live_test_enriched_events.json",
        "current_pipeline_status": "duplicative_source",
        "canonical_projection_status": "complete",
        "notes": ["Enriched duplicate of all/staged family."],
    },
    {
        "dataset_key": "previous-staged-live-events-snapshot",
        "file_path": "data/previous_staged_live_events_snapshot.json",
        "current_pipeline_status": "historical_only",
        "canonical_projection_status": "complete",
        "notes": ["Prior staged snapshot; protected historical compare artifact."],
    },
    {
        "dataset_key": "nycif-major-radar-map-events-legacy",
        "file_path": "nycif_major_radar_map_events.json",
        "current_pipeline_status": "historical_only",
        "canonical_projection_status": "complete",
        "notes": ["Legacy major signal only; not production feed after schema-v1 major builder."],
    },
    {
        "dataset_key": "row-disposition-events",
        "file_path": "data/row_disposition_events.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Disposition audit of open-data rows; not an independent intake source."],
    },
    {
        "dataset_key": "events-schema-v1-staged",
        "file_path": "data/events_schema_v1_staged.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Generated schema-v1 projection."],
    },
    {
        "dataset_key": "events-schema-v1-supplemental-review",
        "file_path": "data/events_schema_v1_supplemental_review.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Generated schema-v1 supplemental projection."],
    },
    {
        "dataset_key": "events-schema-v1-major",
        "file_path": "data/events_schema_v1_major.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Generated major projection."],
    },
    {
        "dataset_key": "schema-v1-approved-pages",
        "file_path": "data/schema-v1/approved/manifest.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Page-shard manifest; generated."],
    },
    {
        "dataset_key": "schema-v1-review-pages",
        "file_path": "data/schema-v1/review/manifest.json",
        "current_pipeline_status": "generated_output",
        "canonical_projection_status": "complete",
        "notes": ["Review page-shard manifest; generated."],
    },
    {
        "dataset_key": "location-cache",
        "file_path": "data/location_cache.json",
        "current_pipeline_status": "historical_only",
        "canonical_projection_status": "n/a",
        "notes": ["Protected GPS memory — not an event feed; never rewritten by this pipeline."],
    },
]


def describe_file(entry: dict) -> dict:
    path = ROOT / entry["file_path"]
    out = {
        "dataset_key": entry["dataset_key"],
        "file_path": entry["file_path"],
        "format": path.suffix.lstrip(".") or "unknown",
        "top_level_shape": None,
        "source_row_count": 0,
        "event_like_row_count": 0,
        "current_pipeline_status": entry["current_pipeline_status"],
        "canonical_projection_status": entry["canonical_projection_status"],
        "notes": list(entry.get("notes") or []),
        "readable": False,
    }
    if not path.exists():
        out["current_pipeline_status"] = "invalid_or_unreadable"
        out["notes"].append("file missing")
        return out
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        out["current_pipeline_status"] = "invalid_or_unreadable"
        out["notes"].append(f"unreadable: {type(exc).__name__}")
        return out
    out["readable"] = True
    if isinstance(payload, list):
        out["top_level_shape"] = "array"
        rows = extract_rows(payload)
        out["source_row_count"] = len(payload)
        out["event_like_row_count"] = len(rows)
    elif isinstance(payload, dict):
        out["top_level_shape"] = "object"
        if "pages" in payload and "total" in payload:
            out["source_row_count"] = int(payload.get("total") or 0)
            out["event_like_row_count"] = int(payload.get("total") or 0)
            out["notes"].append("manifest/total used for page shard inventory")
        elif all(isinstance(v, dict) for v in list(payload.values())[:5]) and "events" not in payload:
            # location_cache-like map
            out["source_row_count"] = len(payload)
            out["event_like_row_count"] = 0
            out["notes"].append("keyed object map — not counted as event rows")
        else:
            rows = extract_rows(payload)
            out["source_row_count"] = len(rows)
            out["event_like_row_count"] = len(rows)
    else:
        out["top_level_shape"] = type(payload).__name__
        out["current_pipeline_status"] = "invalid_or_unreadable"
    return out


def main() -> int:
    sources = [describe_file(e) for e in SOURCE_CATALOG]
    by_status = {}
    for s in sources:
        by_status.setdefault(s["current_pipeline_status"], 0)
        by_status[s["current_pipeline_status"]] += 1

    raw_intake = [
        s
        for s in sources
        if s["dataset_key"]
        in {
            "raw-nyc-open-data-street-events",
            "nyc-citywide-events-calendar",
            "nyc-parks-bigapps-events",
        }
    ]
    generated = [s for s in sources if s["current_pipeline_status"] == "generated_output"]
    duplicative = [s for s in sources if s["current_pipeline_status"] == "duplicative_source"]
    historical = [s for s in sources if s["current_pipeline_status"] == "historical_only"]

    report = {
        "generated_at_utc": __import__("discovery_v02", fromlist=["utc_now"]).utc_now()
        if False
        else None,
        "source_file_count": len(sources),
        "status_counts": by_status,
        "raw_intake_source_row_total": sum(s["event_like_row_count"] for s in raw_intake),
        "generated_output_row_total": sum(s["event_like_row_count"] for s in generated),
        "duplicative_source_row_total": sum(s["event_like_row_count"] for s in duplicative),
        "historical_only_row_total": sum(s["event_like_row_count"] for s in historical),
        "sources": sources,
        "counting_rules": {
            "raw_intake": [
                "data/raw_nyc_open_data_snapshot.json",
                "data/nyc_citywide_events_calendar_snapshot.json",
                "data/nyc_parks_bigapps_events_snapshot.json",
            ],
            "do_not_double_count": [
                "generated schema dumps and page shards",
                "duplicative all-radar / enriched copies",
                "historical snapshots as current intake",
            ],
        },
    }
    from discovery_v02 import utc_now

    report["generated_at_utc"] = utc_now()
    write_json("data/events_source_inventory_v02.json", report)

    lines = [
        "# Events source inventory v02",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        f"- Source files discovered in catalog: **{report['source_file_count']}**",
        f"- Raw intake event-like rows: **{report['raw_intake_source_row_total']}**",
        f"- Generated output rows (excluded from raw intake): **{report['generated_output_row_total']}**",
        f"- Duplicative source rows: **{report['duplicative_source_row_total']}**",
        f"- Historical-only rows: **{report['historical_only_row_total']}**",
        "",
        "## Sources",
        "",
    ]
    for s in sources:
        lines.append(
            f"- `{s['dataset_key']}` — `{s['file_path']}` — status=`{s['current_pipeline_status']}` — rows={s['event_like_row_count']}"
        )
    dump_md("docs/events-source-inventory-v02.md", "\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "source_file_count": report["source_file_count"],
                "raw_intake_source_row_total": report["raw_intake_source_row_total"],
                "generated_output_row_total": report["generated_output_row_total"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
