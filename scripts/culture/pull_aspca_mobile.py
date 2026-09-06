#!/usr/bin/env python3
"""Stage ASPCA Community Medicine mobile pet-care days as calendar rows.

Waitlist / zip-based. No invented van pins. Live schedule scrape is not wired.
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

SOURCE_DATASET = "aspca_community_medicine"


def normalize_raw(raw: dict) -> dict | None:
    title = str(first_present(raw, ("title", "name")) or "").strip()
    zips = first_present(raw, ("zip_codes", "zips"))
    if isinstance(zips, str):
        zip_list = [part.strip() for part in zips.replace("|", ";").split(";") if part.strip()]
    elif isinstance(zips, list):
        zip_list = [str(part).strip() for part in zips if str(part).strip()]
    else:
        zip_list = []
    return normalize_calendar_occurrence(
        occurrence_kind="pet_mobile",
        title=title,
        source_name="aspca",
        source_dataset=SOURCE_DATASET,
        source_event_id=str(first_present(raw, ("source_event_id",)) or "") or None,
        start_at=first_present(raw, ("start_at", "date")),
        end_at=first_present(raw, ("end_at",)),
        borough=str(first_present(raw, ("borough",)) or "").strip() or None,
        display_location=str(first_present(raw, ("location",)) or "").strip() or None,
        address=str(first_present(raw, ("address",)) or "").strip() or None,
        lat=first_present(raw, ("lat", "latitude")),
        lng=first_present(raw, ("lng", "longitude")),
        zip_codes=zip_list,
        waitlist_gated=True,
        source_family="aspca",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.live and not args.fixture:
        print("live ASPCA scrape is not wired; use --fixture. Refusing to invent van pins.", file=sys.stderr)
        return 3
    if not args.fixture:
        print("pass --fixture PATH; refusing to invent ASPCA van days", file=sys.stderr)
        return 2
    raw = load_rows_from_fixture(args.fixture)
    rows = [row for item in raw if (row := normalize_raw(item))]
    write_staging(
        artifact_type="culture_aspca_mobile_staging",
        source_dataset=SOURCE_DATASET,
        rows=rows,
        extra={"waitlist_gated": True, "live_scrape_wired": False, "pin_policy_default": "zip_area_only"},
        staging_name="aspca_mobile.json",
        report_name="aspca_mobile_report.json",
    )
    print(f"staged {len(rows)} ASPCA calendar rows; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
