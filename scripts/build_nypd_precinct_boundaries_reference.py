#!/usr/bin/env python3
"""Download and normalize NYPD precinct boundaries for preview geofences."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso

from tools.supplemental.precinct_geofence import (
    NYC_OPEN_DATA_PRECINCT_URL,
    normalize_precinct_features,
)

REFERENCE_PATH = DATA_DIR / "nypd_precinct_boundaries_reference.json"
REPORT_PATH = DATA_DIR / "reports" / "nypd_precinct_boundaries_reference_report.json"


def fetch_precinct_geojson(url: str = NYC_OPEN_DATA_PRECINCT_URL) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError("precinct geojson missing features array")
    return payload


def build_precinct_reference(refresh: bool = False) -> dict[str, Any]:
    if REFERENCE_PATH.exists() and not refresh:
        existing = load_json_file(REFERENCE_PATH, {})
        if existing.get("artifact_type") == "nypd_precinct_boundaries_reference":
            return {
                "artifact_type": "nypd_precinct_boundaries_reference_report",
                "generated_at_utc": existing.get("generated_at_utc"),
                "qa_pass": True,
                "skipped_download": True,
                "reference_path": repo_relative(REFERENCE_PATH),
                "precinct_count": len(existing.get("precincts") or []),
            }

    raw = fetch_precinct_geojson()
    precincts = normalize_precinct_features(raw.get("features") or [])
    if len(precincts) < 70:
        raise ValueError(f"expected at least 70 precincts, got {len(precincts)}")

    generated_at = utc_now_iso()
    payload = {
        "artifact_type": "nypd_precinct_boundaries_reference",
        "phase": "phase_3b_precinct_geofence",
        "generated_at_utc": generated_at,
        "source_url": NYC_OPEN_DATA_PRECINCT_URL,
        "source_dataset": "nyc_open_data_y76i-bdw7",
        "precinct_count": len(precincts),
        "production_feed": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "precincts": precincts,
    }
    report = {
        "artifact_type": "nypd_precinct_boundaries_reference_report",
        "generated_at_utc": generated_at,
        "qa_pass": True,
        "reference_path": repo_relative(REFERENCE_PATH),
        "precinct_count": len(precincts),
        "source_url": NYC_OPEN_DATA_PRECINCT_URL,
        "skipped_download": False,
    }
    save_json_file(REFERENCE_PATH, payload)
    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    refresh = "--refresh" in sys.argv[1:]
    try:
        report = build_precinct_reference(refresh=refresh)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        report = {
            "artifact_type": "nypd_precinct_boundaries_reference_report",
            "generated_at_utc": utc_now_iso(),
            "qa_pass": False,
            "error": str(exc),
            "reference_path": repo_relative(REFERENCE_PATH),
        }
        save_json_file(REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
