#!/usr/bin/env python3
"""Build unified NYC location gazetteer from public in-repo sources."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.nyc_location_gazetteer import GAZETTEER_PATH, build_gazetteer_index
except ModuleNotFoundError:  # pragma: no cover
    from nyc_location_gazetteer import GAZETTEER_PATH, build_gazetteer_index


def main() -> int:
    built = build_gazetteer_index()
    payload = {
        "artifact_type": "nyc_location_gazetteer",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "index_key_count": built["index_key_count"],
        "source_row_counts": built["source_row_counts"],
        "index": built["index"],
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
        },
    }
    GAZETTEER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GAZETTEER_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    print(json.dumps({k: payload[k] for k in ("generated_at_utc", "index_key_count", "source_row_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
