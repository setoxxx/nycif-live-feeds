#!/usr/bin/env python3
"""Build static schema-v1 page shards + manifests for progressive loading."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import (  # noqa: E402
    SCHEMA_VERSION,
    event_date_key,
    extract_events,
    safe_write_json,
    utc_now,
)

PAGE_SIZE = 750
LAYER_SOURCES = {
    "approved": ROOT / "data" / "events_schema_v1_staged.json",
    "review": ROOT / "data" / "events_schema_v1_supplemental_review.json",
    "major": ROOT / "data" / "events_schema_v1_major.json",
}


def page_meta(events: list[dict]) -> dict:
    dates = [event_date_key(e) for e in events if event_date_key(e)]
    return {
        "count": len(events),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "categories": dict(Counter(e.get("category") for e in events).most_common()),
        "boroughs": dict(Counter(e.get("borough") for e in events).most_common()),
    }


def clear_pages(pages_dir: Path) -> None:
    if not pages_dir.exists():
        pages_dir.mkdir(parents=True, exist_ok=True)
        return
    for old in pages_dir.glob("page-*.json"):
        resolved = old.resolve()
        if resolved.is_relative_to(ROOT.resolve()):
            old.unlink()


def build_layer(name: str, source: Path, out_dir: Path, page_size: int) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    events = extract_events(payload)
    generated = payload.get("generated_at_utc") or utc_now()
    pages_dir = out_dir / "pages"
    clear_pages(pages_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)

    page_entries = []
    total = len(events)
    page_count = max(1, (total + page_size - 1) // page_size) if total else 1

    for i in range(page_count):
        chunk = events[i * page_size : (i + 1) * page_size] if total else []
        page_name = f"page-{i + 1:04d}.json"
        next_cursor = f"page-{i + 2:04d}" if i + 1 < page_count else None
        meta = page_meta(chunk)
        safe_write_json(
            pages_dir / page_name,
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at_utc": generated,
                "total": total,
                "next_cursor": next_cursor,
                "page": page_name,
                "earliest_date": meta["earliest_date"],
                "latest_date": meta["latest_date"],
                "categories": meta["categories"],
                "boroughs": meta["boroughs"],
                "events": chunk,
            },
            root=ROOT,
        )
        page_entries.append(
            {
                "cursor": page_name.replace(".json", ""),
                "page": page_name,
                "path": f"data/schema-v1/{name}/pages/{page_name}",
                "relative_path": f"pages/{page_name}",
                "count": meta["count"],
                "earliest_date": meta["earliest_date"],
                "latest_date": meta["latest_date"],
                "categories": meta["categories"],
                "boroughs": meta["boroughs"],
            }
        )

    dates = [event_date_key(e) for e in events if event_date_key(e)]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "layer": name,
        "generated_at_utc": generated,
        "total": total,
        "page_count": len(page_entries),
        "page_size": page_size,
        "category_counts": dict(Counter(e.get("category") for e in events).most_common()),
        "borough_counts": dict(Counter(e.get("borough") for e in events).most_common()),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "pages": page_entries,
        "full_dump_path": {
            "approved": "data/events_schema_v1_staged.json",
            "review": "data/events_schema_v1_supplemental_review.json",
            "major": "data/events_schema_v1_major.json",
        }.get(name),
    }
    safe_write_json(out_dir / "manifest.json", manifest, root=ROOT)
    if name == "major":
        safe_write_json(out_dir / "events.json", payload, root=ROOT)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = parser.parse_args()

    report = {"generated_at_utc": utc_now(), "page_size": args.page_size, "layers": {}}
    for name, source in LAYER_SOURCES.items():
        out_dir = ROOT / "data" / "schema-v1" / name
        if not source.exists():
            report["layers"][name] = {"error": f"missing {source.name}"}
            continue
        manifest = build_layer(name, source, out_dir, args.page_size)
        report["layers"][name] = {
            "total": manifest["total"],
            "page_count": manifest["page_count"],
            "manifest": f"data/schema-v1/{name}/manifest.json",
        }

    safe_write_json(ROOT / "data" / "events_schema_v1_pages_report.json", report, root=ROOT)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
