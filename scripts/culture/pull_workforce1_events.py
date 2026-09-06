#!/usr/bin/env python3
"""Pull Workforce1 recruitment events (NYC Open Data kf2b-aeh5) into calendar staging.

Real SODA pull. Does not invent events or times. Publication stays off.
Does not write civic people-facing snapshots or event_occurrences.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.civic_people_facing_common import (  # noqa: E402
    combine_local_datetime,
    parse_clock_time,
    parse_iso_date,
)
from scripts.culture.calendar_normalize import normalize_calendar_occurrence  # noqa: E402
from scripts.culture.common import (  # noqa: E402
    WORKFORCE1_EVENTS_DATASET,
    fetch_soda_rows,
    first_present,
    load_rows_from_fixture,
    write_staging,
)


def classify_kind(title: str) -> str:
    lowered = title.lower()
    if "workshop" in lowered or "orientation" in lowered or "info session" in lowered:
        return "workshop"
    return "job_fair"


def normalize_raw(raw: dict) -> dict | None:
    title = str(first_present(raw, ("event_title", "title", "eventname")) or "").strip()
    day = parse_iso_date(first_present(raw, ("event_date", "date", "start_date")))
    start_clock = parse_clock_time(first_present(raw, ("check_in_from", "start_time", "time")))
    end_clock = parse_clock_time(first_present(raw, ("check_in_to", "end_time")))
    start_at = combine_local_datetime(day, start_clock)
    end_at = combine_local_datetime(day, end_clock) if day else None
    source_id = str(
        first_present(raw, ("event_id", "unique_id"))
        or "|".join(
            [
                title,
                str(first_present(raw, ("event_date",)) or ""),
                str(first_present(raw, ("location_name_and_address", "location")) or ""),
            ]
        )
    )
    return normalize_calendar_occurrence(
        occurrence_kind=classify_kind(title),
        title=title,
        source_name="workforce1",
        source_dataset=WORKFORCE1_EVENTS_DATASET,
        source_event_id=source_id,
        start_at=start_at,
        end_at=end_at,
        borough=str(first_present(raw, ("borough", "boro")) or "").strip() or None,
        display_location=str(first_present(raw, ("location",)) or "").strip() or None,
        address=str(
            first_present(raw, ("location_name_and_address", "address")) or ""
        ).strip()
        or None,
        lat=first_present(raw, ("latitude", "lat")),
        lng=first_present(raw, ("longitude", "lng")),
        source_family="workforce1",
        extra={
            "job_family": first_present(raw, ("job_family",)),
            "company_name_or_type": first_present(raw, ("company_name_or_type",)),
            "time_precision": "check_in_window" if start_clock else "date_only",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline SODA-shaped JSON")
    parser.add_argument("--live", action="store_true", help="Pull SODA kf2b-aeh5")
    args = parser.parse_args(argv)

    if args.fixture:
        raw = load_rows_from_fixture(args.fixture)
    elif args.live:
        raw = fetch_soda_rows(WORKFORCE1_EVENTS_DATASET)
    else:
        print("pass --fixture PATH or --live; refusing to invent Workforce1 events", file=sys.stderr)
        return 2

    rows = [row for item in raw if (row := normalize_raw(item))]
    report = write_staging(
        artifact_type="culture_workforce1_calendar_staging",
        source_dataset=WORKFORCE1_EVENTS_DATASET,
        rows=rows,
        extra={
            "occurrence_kinds": sorted({row["occurrence_kind"] for row in rows}),
            "dropped_missing_title_or_date": len(raw) - len(rows),
            "note": "Calendar staging only. Not event_occurrences. publication_allowed=false.",
        },
        staging_name="workforce1_events.json",
        report_name="workforce1_events_report.json",
    )
    print(f"staged {report['row_count']} Workforce1 rows; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
