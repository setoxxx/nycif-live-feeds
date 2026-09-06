#!/usr/bin/env python3
"""Import Howard's curated Culture storefront CSV into staging.

Refuses to invent businesses. Missing CSV is a hard failure.
Every imported row stays pending, promotion_allowed=false, is_sample=false.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.common import (  # noqa: E402
    HOWARD_CSV,
    PLACE_KINDS,
    TEMPLATE_CSV,
    missing_howard_csv_message,
    nyc_point,
    read_csv_rows,
    safety_envelope,
    stable_id,
    write_staging,
)

REQUIRED_COLUMNS = ("business_name",)


def split_tags(value: str) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace("|", ";").split(";")]
    return [part for part in parts if part]


def normalize_row(raw: dict[str, str], *, line_no: int) -> dict:
    name = (raw.get("business_name") or "").strip()
    if not name:
        raise ValueError(f"row {line_no}: business_name is required")
    kind = (raw.get("place_kind") or "storefront").strip() or "storefront"
    if kind not in PLACE_KINDS:
        raise ValueError(f"row {line_no}: unsupported place_kind {kind!r}")
    lat, lng, ok = nyc_point(raw.get("lat"), raw.get("lng"))
    return {
        "business_id": raw.get("business_id") or stable_id("storefront", name, raw.get("address")),
        "business_name": name,
        "qualification_hint": (raw.get("qualification_hint") or name).strip(),
        "address": raw.get("address") or None,
        "borough": raw.get("borough") or None,
        "community_district": raw.get("community_district") or None,
        "lat": lat,
        "lng": lng,
        "coords_in_nyc": ok,
        "cultural_tags": split_tags(raw.get("cultural_tags") or ""),
        "dietary_tags": split_tags(raw.get("dietary_tags") or ""),
        "area_ids": split_tags(raw.get("area_ids") or ""),
        "place_kind": kind,
        "source_url": raw.get("source_url") or None,
        "review_status": "pending",
        "is_sample": False,
        "map_eligible": False,
        **safety_envelope(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=HOWARD_CSV,
        help="Howard curated CSV (required; will not be invented)",
    )
    args = parser.parse_args(argv)

    if not args.csv.exists():
        print(missing_howard_csv_message(args.csv), file=sys.stderr)
        print(f"template: {TEMPLATE_CSV}", file=sys.stderr)
        return 2

    raw_rows = read_csv_rows(args.csv)
    if not raw_rows:
        print("CSV has headers but no storefront rows; refusing to invent any.", file=sys.stderr)
        return 2
    header = set(raw_rows[0].keys())
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        print(f"CSV missing required columns: {missing}", file=sys.stderr)
        return 2

    rows = [normalize_row(raw, line_no=index + 2) for index, raw in enumerate(raw_rows)]
    invented = [row for row in rows if row["business_name"].lower().startswith("sample ")]
    report = write_staging(
        artifact_type="culture_curated_storefronts_staging",
        source_dataset="howard_curated_csv",
        rows=rows,
        extra={
            "csv_path": str(args.csv),
            "accepted_count": 0,
            "pending_count": len(rows),
            "sample_named_rows": len(invented),
            "note": "Pending review. Name is the qualify hint. Do not auto-ACCEPT.",
        },
        staging_name="curated_storefronts.json",
        report_name="curated_storefronts_report.json",
    )
    print(f"staged {report['row_count']} curated rows; 0 ACCEPTED; publication_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
