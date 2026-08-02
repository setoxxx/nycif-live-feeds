#!/usr/bin/env python3
"""Build the fail-closed NYC Parks centroid lookup from NYC Open Data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nycif.normalize.park_geometry import (  # noqa: E402
    DATASET_URL,
    DEFAULT_LOOKUP_PATH,
    load_parks_properties,
    write_park_lookup,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DATASET_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_LOOKUP_PATH)
    args = parser.parse_args(argv)

    rows = load_parks_properties(args.source)
    result = write_park_lookup(rows, args.output)
    report = {
        "qa_pass": bool(result.lookup),
        "source": args.source,
        "source_dataset": "enfh-gkve",
        "source_rows": result.source_rows,
        "geometry_rows": result.geometry_rows,
        "park_groups": result.park_groups,
        "aliases_written": result.aliases_written,
        "ambiguous_alias_count": len(result.ambiguous_aliases),
        "ambiguous_alias_sample": list(result.ambiguous_aliases[:25]),
        "invalid_geometry_rows": result.invalid_geometry_rows,
        "output": str(args.output),
        "promotion_allowed": False,
        "public_map_modified": False,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
