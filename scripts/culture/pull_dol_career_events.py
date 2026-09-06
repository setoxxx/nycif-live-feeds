#!/usr/bin/env python3
"""Stage NYS DOL / Career Center workshops and job fairs (NYC region only).

Source: dol.ny.gov career calendar / Trumba NYC-region events.
Live Trumba fetch is not wired for CI. Fixture rows outside NYC are dropped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.calendar_normalize import (  # noqa: E402
    is_nyc_region,
    normalize_calendar_occurrence,
)
from scripts.culture.common import first_present, load_rows_from_fixture, write_staging  # noqa: E402

SOURCE_DATASET = "nys_dol_trumba"
SOURCE_URL = "https://dol.ny.gov/career-centers"


def classify_kind(title: str) -> str:
    lowered = title.lower()
    if "fair" in lowered or "recruit" in lowered:
        return "job_fair"
    return "workshop"


def normalize_raw(raw: dict) -> dict | None:
    if not is_nyc_region(raw):
        return None
    title = str(first_present(raw, ("title", "event_title", "name")) or "").strip()
    return normalize_calendar_occurrence(
        occurrence_kind=classify_kind(title),
        title=title,
        source_name="nys_dol",
        source_dataset=SOURCE_DATASET,
        source_event_id=str(first_present(raw, ("source_event_id", "event_id")) or "") or None,
        start_at=first_present(raw, ("start_at", "startDateTime", "start", "date")),
        end_at=first_present(raw, ("end_at", "endDateTime", "end")),
        borough=str(first_present(raw, ("borough",)) or "").strip() or None,
        display_location=str(first_present(raw, ("location", "city")) or "").strip() or None,
        address=str(first_present(raw, ("address",)) or "").strip() or None,
        lat=first_present(raw, ("lat", "latitude")),
        lng=first_present(raw, ("lng", "longitude")),
        source_family="nys_dol",
        extra={"region": first_present(raw, ("region", "city"))},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline Trumba-shaped fixture")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved. Live Trumba pull is not wired.",
    )
    args = parser.parse_args(argv)

    if args.live and not args.fixture:
        print(
            "live DOL/Trumba pull is not wired; use --fixture. "
            "Refusing to invent DOL events.",
            file=sys.stderr,
        )
        return 3
    if not args.fixture:
        print("pass --fixture PATH; refusing to invent DOL events", file=sys.stderr)
        return 2

    raw = load_rows_from_fixture(args.fixture)
    rows = [row for item in raw if (row := normalize_raw(item))]
    write_staging(
        artifact_type="culture_dol_career_events_staging",
        source_dataset=SOURCE_DATASET,
        rows=rows,
        extra={
            "source_url": SOURCE_URL,
            "nyc_region_filter": True,
            "source_row_count": len(raw),
            "dropped_non_nyc_or_incomplete": len(raw) - len(rows),
            "live_scrape_wired": False,
            "emoji": "💼",
        },
        staging_name="dol_career_events.json",
        report_name="dol_career_events_report.json",
    )
    print(f"staged {len(rows)} NYC-region DOL rows; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
