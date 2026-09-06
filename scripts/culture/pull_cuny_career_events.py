#!/usr/bin/env python3
"""Compile CUNY public career-event source registry; optionally stage fixture events.

Does not scrape campus pages in CI. Without --events-fixture, writes the
registry and zero invented occurrences.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.calendar_normalize import normalize_calendar_occurrence  # noqa: E402
from scripts.culture.common import (  # noqa: E402
    DATA_DIR,
    first_present,
    load_json,
    load_rows_from_fixture,
    write_staging,
)

DEFAULT_REGISTRY = DATA_DIR / "cuny_career_source_registry.json"
SOURCE_DATASET = "cuny_career_registry"


def classify_kind(title: str) -> str:
    lowered = title.lower()
    if "fair" in lowered:
        return "job_fair"
    return "workshop"


def normalize_raw(raw: dict) -> dict | None:
    title = str(first_present(raw, ("title", "event_title", "name")) or "").strip()
    return normalize_calendar_occurrence(
        occurrence_kind=classify_kind(title),
        title=title,
        source_name="cuny",
        source_dataset=str(first_present(raw, ("source_id",)) or SOURCE_DATASET),
        source_event_id=str(first_present(raw, ("source_event_id", "event_id")) or "") or None,
        start_at=first_present(raw, ("start_at", "start", "date")),
        end_at=first_present(raw, ("end_at", "end")),
        borough=str(first_present(raw, ("borough",)) or "").strip() or None,
        display_location=str(first_present(raw, ("location", "campus")) or "").strip() or None,
        address=str(first_present(raw, ("address",)) or "").strip() or None,
        lat=first_present(raw, ("lat", "latitude")),
        lng=first_present(raw, ("lng", "longitude")),
        source_family="cuny",
        extra={"campus": first_present(raw, ("campus",))},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--events-fixture",
        type=Path,
        help="Optional fixture events. Without this, occurrence count is 0.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved. Live CUNY page scrape is not wired.",
    )
    args = parser.parse_args(argv)

    if args.live and not args.events_fixture:
        print(
            "live CUNY scrape is not wired; pass --events-fixture or compile registry only. "
            "Refusing to invent college fairs.",
            file=sys.stderr,
        )
        return 3
    if not args.registry.exists():
        print(f"CUNY source registry missing: {args.registry}", file=sys.stderr)
        return 2

    registry = load_json(args.registry, {})
    sources = []
    if isinstance(registry, dict) and isinstance(registry.get("sources"), list):
        sources = [row for row in registry["sources"] if isinstance(row, dict)]
    raw: list[dict] = []
    if args.events_fixture:
        raw = load_rows_from_fixture(args.events_fixture)
    rows = [row for item in raw if (row := normalize_raw(item))]
    write_staging(
        artifact_type="culture_cuny_career_events_staging",
        source_dataset=SOURCE_DATASET,
        rows=rows,
        extra={
            "registry_path": str(args.registry),
            "source_count": len(sources),
            "sources": sources,
            "live_scrape_wired": False,
            "emoji": "🎓",
            "note": (
                "Registry compiled. Occurrences only from --events-fixture. "
                "No invented college fairs."
            ),
        },
        staging_name="cuny_career_events.json",
        report_name="cuny_career_events_report.json",
    )
    print(
        f"compiled {len(sources)} CUNY sources; staged {len(rows)} fixture events; "
        "publication_allowed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
