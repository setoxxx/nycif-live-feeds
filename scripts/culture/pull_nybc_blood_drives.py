#!/usr/bin/env python3
"""Stage New York Blood Center mobile drives as calendar occurrences.

CI uses fixtures. Live HTML scrape is not required and is not run in tests.

Scrape / API approach (do not invent drives):
1. Preferred: if donate.nybc.org exposes a public JSON/XHR schedule (zip search
   on the donate site often calls a vendor API), capture that contract in a
   later PR and map only rows with a published site + start time.
2. Fallback: documented HTML parse of public drive listings. Blocked networks
   or CAPTCHA ⇒ skip; never fabricate sites.
3. Pin only when the source row already has in-bounds lat/lng. Otherwise
   list-only / address text.
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

SOURCE = "donate.nybc.org"
SOURCE_DATASET = "nybc_blood_drives"


def normalize_raw(raw: dict) -> dict | None:
    title = str(first_present(raw, ("title", "drive_name", "name")) or "").strip()
    return normalize_calendar_occurrence(
        occurrence_kind="blood_drive",
        title=title,
        source_name="nybc",
        source_dataset=SOURCE_DATASET,
        source_event_id=str(first_present(raw, ("source_event_id", "drive_id")) or "") or None,
        start_at=first_present(raw, ("start_at", "start", "date")),
        end_at=first_present(raw, ("end_at", "end")),
        borough=str(first_present(raw, ("borough",)) or "").strip() or None,
        display_location=str(first_present(raw, ("location", "site_name")) or "").strip() or None,
        address=str(first_present(raw, ("address",)) or "").strip() or None,
        lat=first_present(raw, ("lat", "latitude")),
        lng=first_present(raw, ("lng", "longitude")),
        source_family="nybc",
        extra={"sponsor": first_present(raw, ("sponsor",))},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline fixture (required in CI)")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved. Live NYBC scrape is not wired; exits 3 so CI never depends on it.",
    )
    args = parser.parse_args(argv)

    if args.live and not args.fixture:
        print(
            "live NYBC scrape is not wired in this stub; use --fixture. "
            "Refusing to invent blood drives.",
            file=sys.stderr,
        )
        return 3
    if not args.fixture:
        print("pass --fixture PATH; refusing to invent NYBC drives", file=sys.stderr)
        return 2

    raw = load_rows_from_fixture(args.fixture)
    rows = [row for item in raw if (row := normalize_raw(item))]
    write_staging(
        artifact_type="culture_nybc_blood_drives_staging",
        source_dataset=SOURCE_DATASET,
        rows=rows,
        extra={
            "source_url": f"https://{SOURCE}",
            "live_scrape_wired": False,
            "emoji": "🩸",
            "dropped_missing_title_or_date": len(raw) - len(rows),
        },
        staging_name="nybc_blood_drives.json",
        report_name="nybc_blood_drives_report.json",
    )
    print(f"staged {len(rows)} NYBC fixture rows; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
