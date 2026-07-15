#!/usr/bin/env python3
"""Daily people-facing / photographer desk sync orchestrator (fail-closed).

Safe subset: does NOT rebuild location_cache, nycif_staged_live_events,
staged_live_manifest, or previous_staged snapshot.

Writes data/daily_people_facing_sync_report.json.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, utc_now  # noqa: E402

PROTECTED = [
    DATA_DIR / "location_cache.json",
    DATA_DIR / "nycif_staged_live_events.json",
    DATA_DIR / "staged_live_manifest.json",
    DATA_DIR / "previous_staged_live_events_snapshot.json",
]


def file_fingerprint(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    st = path.stat()
    return (st.st_size, int(st.st_mtime_ns))


def run_step(cmd: list[str], *, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    import os

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "ok": proc.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-network-sync",
        action="store_true",
        help="Skip live SODA/calendar/parks fetches; rebuild from committed snapshots",
    )
    parser.add_argument("--reference-today", default=None)
    args = parser.parse_args()

    before = {str(p): file_fingerprint(p) for p in PROTECTED}
    steps: list[dict[str, Any]] = []
    generated = utc_now()

    if not args.skip_network_sync:
        steps.append(run_step([sys.executable, "scripts/sync_nyc_open_data.py"]))
        steps.append(run_step([sys.executable, "scripts/sync_nyc_citywide_events_calendar.py"]))
        steps.append(run_step([sys.executable, "scripts/sync_nyc_parks_bigapps_events.py"]))
        steps.append(run_step([sys.executable, "scripts/sync_civic_people_facing_sources.py"]))

    civic_build = [sys.executable, "scripts/build_civic_people_facing_staging.py"]
    if args.reference_today:
        civic_build += ["--reference-today", args.reference_today]
    steps.append(run_step(civic_build))
    steps.append(run_step([sys.executable, "scripts/build_civic_people_facing_map_coverage.py"]))

    photo = [sys.executable, "scripts/build_photographer_assignment_calendar.py"]
    if args.reference_today:
        photo += ["--reference-today", args.reference_today]
    steps.append(run_step(photo))
    # Discovery first, then civic God View so civic bookmark is re-injected last.
    if (ROOT / "scripts" / "build_events_discovery_godview_digest_v02.py").exists():
        steps.append(run_step([sys.executable, "scripts/build_events_discovery_godview_digest_v02.py"]))
    steps.append(run_step([sys.executable, "scripts/build_civic_people_facing_godview_digest.py"]))

    after = {str(p): file_fingerprint(p) for p in PROTECTED}
    protected_changed = [p for p in after if before.get(p) != after.get(p)]

    staging_qa = load_json(DATA_DIR / "civic_people_facing_date_time_location_qa.json", {})
    coverage = load_json(DATA_DIR / "civic_people_facing_map_coverage_report.json", {})
    photo_report = load_json(DATA_DIR / "photographer_assignment_calendar_report.json", {})

    qa_pass = (
        all(s.get("ok") for s in steps)
        and not protected_changed
        and bool(staging_qa.get("qa_pass", True))
        and bool(coverage.get("qa_pass", True))
        and bool(photo_report.get("qa_pass", False))
    )

    report = {
        "schema_version": "daily-people-facing-desk-sync-v1",
        "generated_at_utc": generated,
        "qa_pass": qa_pass,
        "skip_network_sync": bool(args.skip_network_sync),
        "steps": [
            {"cmd": s["cmd"], "ok": s["ok"], "exit_code": s["exit_code"]} for s in steps
        ],
        "failed_steps": [s["cmd"] for s in steps if not s["ok"]],
        "protected_files_changed": protected_changed,
        "protected_files_untouched": len(protected_changed) == 0,
        "civic": {
            "date_time_location_qa_pass": staging_qa.get("qa_pass"),
            "map_coverage_qa_pass": coverage.get("qa_pass"),
            "accepted": coverage.get("accepted_count"),
            "map_ready": (coverage.get("coordinate_status_counts_staging") or {}).get("map_ready"),
            "list_only": (coverage.get("coordinate_status_counts_staging") or {}).get("list_only"),
        },
        "photographer_calendar": {
            "qa_pass": photo_report.get("qa_pass"),
            "total_events": photo_report.get("total_events"),
            "days_with_coverage": photo_report.get("days_with_coverage"),
            "month_counts": photo_report.get("month_counts"),
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": (
            "Safe daily desk sync. Does not run build_staged_production_feed / "
            "build_location_cache / public WordPress publish. Full permit→staged "
            "refresh remains live-sync-qa (manual dispatch)."
        ),
    }
    save_json(DATA_DIR / "daily_people_facing_sync_report.json", report)

    # Attach daily pull marker into civic godview digest if present.
    civic_gv = load_json(DATA_DIR / "civic_people_facing_godview_digest.json", None)
    if isinstance(civic_gv, dict):
        civic_gv["daily_pull"] = {
            "last_run_utc": generated,
            "qa_pass": qa_pass,
            "report": "data/daily_people_facing_sync_report.json",
            "photographer_calendar_events": photo_report.get("total_events"),
            "photographer_days_with_coverage": photo_report.get("days_with_coverage"),
        }
        save_json(DATA_DIR / "civic_people_facing_godview_digest.json", civic_gv)

    print(
        f"daily desk sync qa_pass={qa_pass} "
        f"photo_events={photo_report.get('total_events')} "
        f"protected_untouched={report['protected_files_untouched']}"
    )
    if not qa_pass:
        for s in steps:
            if not s["ok"]:
                print(f"FAIL {s['cmd']}\n{s['stderr_tail']}", file=sys.stderr)
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
