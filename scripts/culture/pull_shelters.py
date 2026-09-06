#!/usr/bin/env python3
"""Stage shelter rows from NYC Open Data g9nt-57fp.

Prefer an addressable directory. If the dataset is census-only (borough counts,
no address / lat / lng), do not invent pins.
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
    SHELTER_DATASET,
    first_present,
    fetch_soda_rows,
    load_rows_from_fixture,
    nyc_point,
    row_looks_addressable,
    safety_envelope,
    stable_id,
    write_staging,
)

RELATED_ADDRESSABLE = (
    ("homeless_drop_in", "bmxf-3rd4"),
    ("homebase", "ntcm-2w4k"),
)


def normalize_row(raw: dict[str, Any], *, census_only: bool) -> dict[str, Any]:
    name = str(
        first_present(raw, ("center_name", "facility_name", "name", "shelter_name")) or ""
    ).strip()
    address = first_present(raw, ("address", "street_address", "location"))
    borough = first_present(raw, ("borough", "boro"))
    lat, lng, ok = nyc_point(
        first_present(raw, ("latitude", "lat")),
        first_present(raw, ("longitude", "lng", "lon")),
    )
    source_id = str(
        first_present(raw, ("unique_id", "objectid", "center_name")) or name or borough or ""
    ).strip()
    return {
        "facility_id": stable_id("shelter", SHELTER_DATASET, source_id, name, borough),
        "place_kind": "shelter",
        "source_dataset": SHELTER_DATASET,
        "source_facility_id": source_id or stable_id(name, borough)[:16],
        "display_name": name or f"Shelter census row ({borough or 'unknown'})",
        "address": None if census_only else address,
        "borough": borough,
        "lat": None if census_only else lat,
        "lng": None if census_only else lng,
        "addressable": (not census_only) and (bool(address) or ok),
        "pin_policy": "list_only",
        "map_eligible": False,
        "census_only": census_only,
        "confidence_reason": (
            "g9nt-57fp payload looks census-only; prefer an addressable shelter "
            "directory over invented pins. Related civic snapshots: bmxf-3rd4, ntcm-2w4k."
            if census_only
            else "Addressable fields present; still pending human review."
        ),
        **safety_envelope(),
    }


def detect_census_only(raw: list[dict[str, Any]]) -> bool:
    if not raw:
        return True
    return not any(row_looks_addressable(row) for row in raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline JSON fixture")
    parser.add_argument("--live", action="store_true", help="Pull SODA (optional)")
    args = parser.parse_args(argv)

    if args.fixture:
        raw = load_rows_from_fixture(args.fixture)
    elif args.live:
        raw = fetch_soda_rows(SHELTER_DATASET)
    else:
        print("pass --fixture PATH or --live; refusing to invent shelters", file=sys.stderr)
        return 2

    census_only = detect_census_only(raw)
    rows = [normalize_row(item, census_only=census_only) for item in raw]
    report = write_staging(
        artifact_type="culture_shelters_staging",
        source_dataset=SHELTER_DATASET,
        rows=rows,
        extra={
            "census_only": census_only,
            "addressable_row_count": sum(1 for row in rows if row.get("addressable")),
            "related_addressable_datasets": [item[1] for item in RELATED_ADDRESSABLE],
            "note": (
                "Census-only: no shelter pins. Choose an addressable directory before review."
                if census_only
                else "Address fields seen; pins still pending review and layer gates."
            ),
        },
        staging_name="shelters.json",
        report_name="shelters_report.json",
    )
    print(
        f"staged {report['row_count']} shelter rows; census_only={census_only}; "
        "publication_allowed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
