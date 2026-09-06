#!/usr/bin/env python3
"""Fail-closed Culture publication gate.

Default expected outcome: qa_pass (scaffold healthy) and publication_allowed=false.
Never flips reader gates. Never invents storefronts.
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
    HOWARD_CSV,
    REPORT_DIR,
    STAGING_DIR,
    default_reader_gates,
    load_json,
    nyc_point,
    save_json,
    utc_now,
)

PROTECTED = (
    "data/location_cache.json",
    "data/nycif_staged_live_events.json",
    "data/staged_live_manifest.json",
    "data/previous_staged_live_events_snapshot.json",
)


def _rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path, {})
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [row for row in payload["rows"] if isinstance(row, dict)]
    return []


def _gate_false(settings: dict[str, bool]) -> list[str]:
    return [name for name, value in settings.items() if value]


def validate(settings: dict[str, bool] | None = None) -> dict[str, Any]:
    gates = default_reader_gates()
    if settings:
        gates.update({key: bool(value) for key, value in settings.items() if key in gates})

    failures: list[str] = []
    notes: list[str] = []

    storefronts = _rows(STAGING_DIR / "curated_storefronts.json")
    civic = {
        "nypd": _rows(STAGING_DIR / "nypd_precincts.json"),
        "fdny": _rows(STAGING_DIR / "fdny_firehouses.json"),
        "shelter": _rows(STAGING_DIR / "shelters.json"),
    }

    if not HOWARD_CSV.exists() and not storefronts:
        notes.append("Howard ~91 CSV not dropped; zero curated storefronts (correct, not invented).")

    accepted = [row for row in storefronts if str(row.get("review_status")) == "ACCEPTED"]
    samples = [row for row in storefronts if row.get("is_sample") is True]
    promoted = [
        row
        for row in storefronts
        if row.get("promotion_allowed") is True or row.get("map_eligible") is True
    ]
    if accepted:
        failures.append(f"{len(accepted)} curated rows marked ACCEPTED without Phase C6 reviewer packet")
    if samples:
        failures.append("staging curated file contains is_sample=true rows")
    if promoted:
        failures.append("staging curated file has promotion_allowed or map_eligible true")

    for row in storefronts:
        lat, lng, ok = nyc_point(row.get("lat"), row.get("lng"))
        if (row.get("lat") is not None or row.get("lng") is not None) and not ok:
            failures.append(f"out-of-bounds coords on {row.get('business_name')}")
        if not row.get("business_name"):
            failures.append("curated row missing business_name")
        if row.get("manual_review_status") not in (None, "pending"):
            # Reviewer may later set approved; scaffold staging must stay pending.
            if row.get("manual_review_status") == "approved" and row.get("promotion_allowed"):
                failures.append("approved+promoted row in staging")

    shelter_payload = load_json(STAGING_DIR / "shelters.json", {})
    if isinstance(shelter_payload, dict) and shelter_payload.get("census_only"):
        pinned = [row for row in civic["shelter"] if row.get("lat") or row.get("map_eligible")]
        if pinned:
            failures.append("census-only shelter staging has pins")
        notes.append("Shelter dataset treated as census-only; pins correctly omitted.")

    enabled = _gate_false(gates)
    if enabled:
        failures.append(f"reader gates still enabled: {enabled}")

    publication_allowed = False
    # Explicit future path: all gates still false here, so never true.
    if (
        not enabled
        and accepted
        and not samples
        and not promoted
        and all(row.get("manual_reviewer") for row in accepted)
        and all(row.get("approval_decision_reason") for row in accepted)
        and all(row.get("promotion_allowed") for row in accepted)
    ):
        publication_allowed = False  # still require a human Phase C6 command
        notes.append("ACCEPTED packet present but Phase C6 is not authorized by this scaffold.")

    qa_pass = not failures
    report = {
        "artifact_type": "culture_community_validate_before_publish",
        "generated_at_utc": utc_now(),
        "qa_pass": qa_pass,
        "publication_allowed": publication_allowed,
        "would_publish": False,
        "reader_gates": gates,
        "curated_row_count": len(storefronts),
        "accepted_count": len(accepted),
        "civic_row_counts": {key: len(value) for key, value in civic.items()},
        "howard_csv_present": HOWARD_CSV.exists(),
        "protected_files_untouched": list(PROTECTED),
        "wordpress_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "invented_storefronts": False,
        "failures": failures,
        "notes": notes,
    }
    save_json(REPORT_DIR / "validate_before_publish.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings-json",
        type=Path,
        help="Optional override of reader gates (tests). Production uses defaults (all false).",
    )
    args = parser.parse_args(argv)
    settings = load_json(args.settings_json, None) if args.settings_json else None
    if settings is not None and not isinstance(settings, dict):
        print("settings-json must be an object", file=sys.stderr)
        return 2
    report = validate(settings)
    print(
        f"qa_pass={report['qa_pass']} publication_allowed={report['publication_allowed']} "
        f"accepted={report['accepted_count']}"
    )
    if report["failures"]:
        for item in report["failures"]:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
