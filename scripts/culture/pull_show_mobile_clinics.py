#!/usr/bin/env python3
"""Stage NYC H+H S.H.O.W. mobile clinic / resource-van days.

Only rows with a start time become calendar occurrences. Address optional
(list-only if no certified coords). Live scrape is not wired for CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.calendar_normalize import normalize_calendar_occurrence  # noqa: E402
from scripts.culture.common import first_present, load_rows_from_fixture, write_staging  # noqa: E402

SOURCE_DATASET = "hh_show_mobile"
SOURCE_URL = "https://www.nychealthandhospitals.org/community-care/street-health-outreach-and-wellness/"


def classify_kind(raw: dict) -> str:
    text = " ".join(
        str(raw.get(key) or "") for key in ("kind", "program", "title", "service")
    ).lower()
    if "resource van" in text or ("van" in text and "clinic" not in text):
        return "resource_van"
    return "mobile_clinic"


def normalize_raw(raw: dict) -> dict | None:
    title = str(first_present(raw, ("title", "site_name", "name")) or "").strip()
    return normalize_calendar_occurrence(
        occurrence_kind=classify_kind(raw),
        title=title,
        source_name="hh_show",
        source_dataset=SOURCE_DATASET,
        source_event_id=str(first_present(raw, ("source_event_id", "unit_id")) or "") or None,
        start_at=first_present(raw, ("start_at", "start", "date")),
        end_at=first_present(raw, ("end_at", "end")),
        borough=str(first_present(raw, ("borough",)) or "").strip() or None,
        display_location=str(first_present(raw, ("location", "site_name")) or "").strip() or None,
        address=str(first_present(raw, ("address",)) or "").strip() or None,
        lat=first_present(raw, ("lat", "latitude")),
        lng=first_present(raw, ("lng", "longitude")),
        source_family="hh_show",
        extra={"program": first_present(raw, ("program", "service"))},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline fixture (required in CI)")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved. Live H+H schedule scrape is not wired.",
    )
    args = parser.parse_args(argv)

    if args.live and not args.fixture:
        print(
            "live H+H SHOW scrape is not wired; use --fixture. "
            "Refusing to invent mobile clinics.",
            file=sys.stderr,
        )
        return 3
    if not args.fixture:
        print("pass --fixture PATH; refusing to invent SHOW clinics", file=sys.stderr)
        return 2

    raw = load_rows_from_fixture(args.fixture)
    rows = [row for item in raw if (row := normalize_raw(item))]
    write_staging(
        artifact_type="culture_show_mobile_clinics_staging",
        source_dataset=SOURCE_DATASET,
        rows=rows,
        extra={
            "source_url": SOURCE_URL,
            "live_scrape_wired": False,
            "emoji": "🏥",
            "dropped_missing_title_or_date": len(raw) - len(rows),
        },
        staging_name="show_mobile_clinics.json",
        report_name="show_mobile_clinics_report.json",
    )
    print(f"staged {len(rows)} SHOW fixture rows; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
