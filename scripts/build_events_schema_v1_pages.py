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

from schema_v1_common import SCHEMA_VERSION, event_date_key, extract_events, utc_now  # noqa: E402

PAGE_SIZE = 750


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def build_layer(name: str, source: Path, out_dir: Path, page_size: int) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    events = extract_events(payload)
    generated = payload.get("generated_at_utc") or utc_now()
    pages_dir = out_dir / "pages"
    if pages_dir.exists():
        for old in pages_dir.glob("page-*.json"):
            old.unlink()
    pages_dir.mkdir(parents=True, exist_ok=True)

    page_paths = []
    total = len(events)
    page_count = max(1, (total + page_size - 1) // page_size) if total else 1
    if total == 0:
        page_name = "page-0001.json"
        write_json(
            pages_dir / page_name,
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at_utc": generated,
                "total": 0,
                "next_cursor": None,
                "events": [],
            },
        )
        page_paths.append(f"pages/{page_name}")
    else:
        for i in range(page_count):
            chunk = events[i * page_size : (i + 1) * page_size]
            page_name = f"page-{i+1:04d}.json"
            next_cursor = f"page-{i+2:04d}" if i + 1 < page_count else None
            write_json(
                pages_dir / page_name,
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at_utc": generated,
                    "total": total,
                    "next_cursor": next_cursor,
                    "events": chunk,
                },
            )
            page_paths.append(f"pages/{page_name}")

    dates = [event_date_key(e) for e in events if event_date_key(e)]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "layer": name,
        "generated_at_utc": generated,
        "total": total,
        "page_count": len(page_paths),
        "page_size": page_size,
        "category_counts": dict(Counter(e.get("category") for e in events).most_common()),
        "borough_counts": dict(Counter(e.get("borough") for e in events).most_common()),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "pages": [
            {
                "cursor": path.replace("pages/", "").replace(".json", ""),
                "path": f"data/schema-v1/{name}/{path}",
                "relative_path": path,
            }
            for path in page_paths
        ],
        "full_dump_path": {
            "approved": "data/events_schema_v1_staged.json",
            "review": "data/events_schema_v1_supplemental_review.json",
            "major": "data/events_schema_v1_major.json",
        }.get(name),
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = parser.parse_args()

    layers = [
        ("approved", ROOT / "data" / "events_schema_v1_staged.json", ROOT / "data" / "schema-v1" / "approved"),
        ("review", ROOT / "data" / "events_schema_v1_supplemental_review.json", ROOT / "data" / "schema-v1" / "review"),
        ("major", ROOT / "data" / "events_schema_v1_major.json", ROOT / "data" / "schema-v1" / "major"),
    ]
    report = {"generated_at_utc": utc_now(), "page_size": args.page_size, "layers": {}}
    for name, source, out_dir in layers:
        if not source.exists():
            report["layers"][name] = {"error": f"missing {source}"}
            continue
        manifest = build_layer(name, source, out_dir, args.page_size)
        # Convenience: major also as single events.json
        if name == "major":
            payload = json.loads(source.read_text(encoding="utf-8"))
            write_json(out_dir / "events.json", payload)
        report["layers"][name] = {
            "total": manifest["total"],
            "page_count": manifest["page_count"],
            "manifest": str((out_dir / "manifest.json").relative_to(ROOT)),
        }

    write_json(ROOT / "data" / "events_schema_v1_pages_report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
