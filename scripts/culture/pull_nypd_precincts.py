#!/usr/bin/env python3
"""Stage NYPD precinct polygons from NYC Open Data y76i-bdw7.

Staging only. Does not pin invented precinct houses. Does not enable publication.
Does not rewrite data/nypd_precinct_boundaries_reference.json.
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
    NYPD_DATASET,
    first_present,
    load_rows_from_fixture,
    fetch_soda_rows,
    safety_envelope,
    stable_id,
    write_staging,
)


def _feature_to_row(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else feature
    precinct = str(
        first_present(props, ("precinct", "Precinct", "precinct_name")) or ""
    ).strip()
    if not precinct:
        return None
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
    return {
        "facility_id": stable_id("nypd", NYPD_DATASET, precinct),
        "place_kind": "civic_nypd",
        "source_dataset": NYPD_DATASET,
        "source_facility_id": precinct,
        "display_name": f"{precinct} Precinct" if precinct.isdigit() else precinct,
        "emoji": "👮",
        "address": None,
        "borough": first_present(props, ("borough", "boro")),
        "lat": None,
        "lng": None,
        "addressable": False,
        "geometry_type": (geometry or {}).get("type"),
        "has_polygon": bool(geometry),
        "pin_policy": "list_only",
        "confidence_reason": (
            "y76i-bdw7 is a precinct boundary dataset. House pins require an "
            "official precinct-house address; do not invent centroids."
        ),
        **safety_envelope(),
    }


def normalize_rows(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw:
        row = _feature_to_row(item)
        if row:
            rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline GeoJSON/JSON fixture")
    parser.add_argument("--live", action="store_true", help="Pull SODA (optional)")
    args = parser.parse_args(argv)

    if args.fixture:
        raw = load_rows_from_fixture(args.fixture)
    elif args.live:
        raw = fetch_soda_rows(NYPD_DATASET)
    else:
        print("pass --fixture PATH or --live; refusing to invent precincts", file=sys.stderr)
        return 2

    rows = normalize_rows(raw)
    report = write_staging(
        artifact_type="culture_nypd_precincts_staging",
        source_dataset=NYPD_DATASET,
        rows=rows,
        extra={
            "note": "Boundary staging only. 👮 house pins stay off until addressable review.",
            "place_kind": "civic_nypd",
        },
        staging_name="nypd_precincts.json",
        report_name="nypd_precincts_report.json",
    )
    print(f"staged {report['row_count']} precincts; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
