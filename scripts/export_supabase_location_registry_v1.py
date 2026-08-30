#!/usr/bin/env python3
"""Export the durable Supabase location registry for one production transaction.

The export is runtime-only. It gives the canonical projector a read-only snapshot
of places already learned in prior runs so future event occurrences can reuse
those locations without geocoding them again.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_OUTPUT = Path("/tmp/nycif-location-registry-v1.json")
PAGE_SIZE = 1000


def fetch_rows(base: str, key: str, table: str, select: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urlencode({"select": select, "order": "location_id.asc"})
        request = Request(
            f"{base}/rest/v1/{table}?{query}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Range": f"{offset}-{offset + PAGE_SIZE - 1}",
                "Prefer": "count=exact",
            },
        )
        with urlopen(request, timeout=120) as response:  # nosec B310 - configured Supabase HTTPS URL
            page = json.load(response)
        if not isinstance(page, list):
            raise RuntimeError(f"unexpected {table} response")
        rows.extend(item for item in page if isinstance(item, dict))
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def export(output: Path) -> dict[str, Any]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    locations = fetch_rows(
        base,
        key,
        "locations",
        "location_id,borough,canonical_name,canonical_full_name,latitude,longitude,precision,location_authority,confidence,review_required,source_cemsid,updated_at,metadata",
    )
    aliases = fetch_rows(
        base,
        key,
        "location_aliases",
        "location_id,raw_alias,normalized_alias,source_dataset,occurrence_count,first_seen,last_seen,metadata",
    )

    known_ids = {str(row.get("location_id") or "") for row in locations}
    aliases = [row for row in aliases if str(row.get("location_id") or "") in known_ids]
    payload = {
        "schema_version": "NYCIF_LOCATION_REGISTRY_RUNTIME_V1",
        "location_count": len(locations),
        "alias_count": len(aliases),
        "locations": locations,
        "aliases": aliases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "location_count": len(locations), "alias_count": len(aliases)}, sort_keys=True))
    if not locations or not aliases:
        raise RuntimeError("durable location registry export is unexpectedly empty")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
