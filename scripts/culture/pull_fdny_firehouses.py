#!/usr/bin/env python3
"""Stage FDNY firehouses from NYC Open Data hc8x-tcnd.

Staging only. Pins require in-bounds coords from the city row. No invented houses.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.common import (  # noqa: E402
    FDNY_DATASET,
    first_present,
    fetch_soda_rows,
    load_rows_from_fixture,
    nyc_point,
    safety_envelope,
    stable_id,
    write_staging,
)


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(
        first_present(raw, ("facilityname", "facility_name", "name", "company")) or ""
    ).strip()
    address = first_present(
        raw, ("facilityaddress", "facility_address", "address", "streetaddress")
    )
    borough = first_present(raw, ("borough", "boro"))
    source_id = str(
        first_present(raw, ("bin", "objectid", "facilityname", "name")) or name or address or ""
    ).strip()
    lat, lng, ok = nyc_point(
        first_present(raw, ("latitude", "lat", "y")),
        first_present(raw, ("longitude", "lng", "lon", "long", "x")),
    )
    return {
        "facility_id": stable_id("fdny", FDNY_DATASET, source_id, name, address),
        "place_kind": "civic_fdny",
        "source_dataset": FDNY_DATASET,
        "source_facility_id": source_id or stable_id(name, address)[:16],
        "display_name": name or "FDNY firehouse",
        "emoji": "🚒",
        "address": address,
        "borough": borough,
        "lat": lat,
        "lng": lng,
        "addressable": bool(address) or ok,
        "pin_policy": "list_only" if not ok else "pending_review",
        "map_eligible": False,
        **safety_envelope(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline JSON fixture")
    parser.add_argument("--live", action="store_true", help="Pull SODA (optional)")
    args = parser.parse_args(argv)

    if args.fixture:
        raw = load_rows_from_fixture(args.fixture)
    elif args.live:
        raw = fetch_soda_rows(FDNY_DATASET)
    else:
        print("pass --fixture PATH or --live; refusing to invent firehouses", file=sys.stderr)
        return 2

    rows = [normalize_row(item) for item in raw]
    report = write_staging(
        artifact_type="culture_fdny_firehouses_staging",
        source_dataset=FDNY_DATASET,
        rows=rows,
        extra={"place_kind": "civic_fdny", "emoji": "🚒"},
        staging_name="fdny_firehouses.json",
        report_name="fdny_firehouses_report.json",
    )
    print(f"staged {report['row_count']} firehouses; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
