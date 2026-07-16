#!/usr/bin/env python3
"""Daily people-facing / photographer desk sync orchestrator (fail-closed).

Safe subset: does NOT rebuild location_cache, nycif_staged_live_events,
staged_live_manifest, or previous_staged snapshot.

Writes data/daily_people_facing_sync_report.json.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
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


ALLOWED_SCRIPTS = frozenset(
    {
        "scripts/sync_nyc_open_data.py",
        "scripts/sync_nyc_citywide_events_calendar.py",
        "scripts/sync_nyc_parks_bigapps_events.py",
        "scripts/sync_civic_people_facing_sources.py",
        "scripts/build_civic_people_facing_staging.py",
        "scripts/build_civic_people_facing_map_coverage.py",
        "scripts/build_photographer_assignment_calendar.py",
        "scripts/build_photographer_money_day_packs.py",
        "scripts/sync_nyc_permits_historical.py",
        "scripts/build_photographer_viral_recurrence.py",
        "scripts/build_citywide_parade_census.py",
        "scripts/build_news_desk_assignment_checklist.py",
        "scripts/build_pin_integrity_gate.py",
        "scripts/build_photographer_shoot_day_certified.py",
        "scripts/build_events_discovery_godview_digest_v02.py",
        "scripts/build_civic_people_facing_godview_digest.py",
    }
)


def validated_reference_today(value: str | None) -> str | None:
    """Return YYYY-MM-DD or None. Rejects any non-ISO value before OS exec."""
    if value is None or value == "":
        return None
    cleaned = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        raise SystemExit("Invalid --reference-today (expected YYYY-MM-DD)")
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError as exc:
        raise SystemExit("Invalid --reference-today date") from exc
    if parsed.year < 2020 or parsed.year > 2100:
        raise SystemExit("Invalid --reference-today year")
    return parsed.isoformat()


def safe_python_script(script: str, *extra: str) -> list[str]:
    if script not in ALLOWED_SCRIPTS:
        raise SystemExit(f"Refusing non-allowlisted script: {script}")
    argv = [sys.executable, script, *extra]
    return argv



def file_fingerprint(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    st = path.stat()
    return (st.st_size, int(st.st_mtime_ns))


def run_step(cmd: list[str], *, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    import os

    if not cmd or not isinstance(cmd, list) or any(not isinstance(x, str) for x in cmd):
        raise SystemExit("run_step requires a list[str] argv")
    if Path(cmd[0]).resolve() != Path(sys.executable).resolve():
        raise SystemExit("run_step may only invoke this Python interpreter")
    if len(cmd) < 2 or cmd[1] not in ALLOWED_SCRIPTS:
        raise SystemExit("run_step script is not allowlisted")
    # Extra args: only fixed flags + validated ISO dates (pythonsecurity:S8705).
    i = 2
    while i < len(cmd):
        token = cmd[i]
        if token == "--reference-today":
            if i + 1 >= len(cmd) or validated_reference_today(cmd[i + 1]) is None:
                raise SystemExit("Invalid --reference-today in argv")
            i += 2
            continue
        if token == "--skip-network":
            i += 1
            continue
        if token.startswith("--"):
            raise SystemExit(f"Unsupported flag in daily sync argv: {token}")
        raise SystemExit(f"Unsupported positional arg in daily sync argv: {token}")
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
        shell=False,
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

    reference_today = validated_reference_today(args.reference_today)
    ref_args = ["--reference-today", reference_today] if reference_today else []

    if not args.skip_network_sync:
        steps.append(run_step(safe_python_script("scripts/sync_nyc_open_data.py")))
        steps.append(run_step(safe_python_script("scripts/sync_nyc_citywide_events_calendar.py")))
        steps.append(run_step(safe_python_script("scripts/sync_nyc_parks_bigapps_events.py")))
        steps.append(run_step(safe_python_script("scripts/sync_civic_people_facing_sources.py")))

    steps.append(run_step(safe_python_script("scripts/build_civic_people_facing_staging.py", *ref_args)))
    steps.append(run_step(safe_python_script("scripts/build_civic_people_facing_map_coverage.py")))
    steps.append(run_step(safe_python_script("scripts/build_photographer_assignment_calendar.py", *ref_args)))
    steps.append(run_step(safe_python_script("scripts/build_photographer_money_day_packs.py", *ref_args)))
    hist_args = list(ref_args)
    if args.skip_network_sync:
        hist_args.append("--skip-network")
    steps.append(run_step(safe_python_script("scripts/sync_nyc_permits_historical.py", *hist_args)))
    steps.append(run_step(safe_python_script("scripts/build_photographer_viral_recurrence.py", *ref_args)))
    steps.append(run_step(safe_python_script("scripts/build_citywide_parade_census.py")))
    steps.append(run_step(safe_python_script("scripts/build_news_desk_assignment_checklist.py")))
    # Pin integrity fail-closed: after calendar/packs/viral/civic coverage rebuilds.
    steps.append(run_step(safe_python_script("scripts/build_pin_integrity_gate.py")))
    steps.append(run_step(safe_python_script("scripts/build_photographer_shoot_day_certified.py", *ref_args)))
    # Discovery first, then civic God View so civic bookmark is re-injected last.
    if (ROOT / "scripts" / "build_events_discovery_godview_digest_v02.py").exists():
        steps.append(run_step(safe_python_script("scripts/build_events_discovery_godview_digest_v02.py")))
    steps.append(run_step(safe_python_script("scripts/build_civic_people_facing_godview_digest.py")))

    after = {str(p): file_fingerprint(p) for p in PROTECTED}
    protected_changed = [p for p in after if before.get(p) != after.get(p)]

    staging_qa = load_json(DATA_DIR / "civic_people_facing_date_time_location_qa.json", {})
    coverage = load_json(DATA_DIR / "civic_people_facing_map_coverage_report.json", {})
    photo_report = load_json(DATA_DIR / "photographer_assignment_calendar_report.json", {})
    quality_report = load_json(DATA_DIR / "photographer_money_day_quality_report.json", {})
    pack_report = load_json(DATA_DIR / "photographer_money_day_pack_report.json", {})
    viral_report = load_json(DATA_DIR / "photographer_viral_recurrence_report.json", {})
    parade_census_report = load_json(DATA_DIR / "citywide_parade_census_report.json", {})
    news_desk_report = load_json(DATA_DIR / "news_desk_assignment_checklist_report.json", {})
    hist_report = load_json(DATA_DIR / "nyc_permits_historical_sync_report.json", {})
    pin_report = load_json(DATA_DIR / "pin_integrity_gate_report.json", {})
    shoot_report = load_json(DATA_DIR / "photographer_shoot_day_certified_report.json", {})

    qa_pass = (
        all(s.get("ok") for s in steps)
        and not protected_changed
        and bool(staging_qa.get("qa_pass", True))
        and bool(coverage.get("qa_pass", True))
        and bool(photo_report.get("qa_pass", False))
        and bool(quality_report.get("qa_pass", False))
        and bool(pack_report.get("qa_pass", False))
        and bool(hist_report.get("qa_pass", False))
        and bool(viral_report.get("qa_pass", False))
        and bool(parade_census_report.get("qa_pass", False))
        and bool(news_desk_report.get("qa_pass", False))
        and bool(pin_report.get("qa_pass", False))
        and bool(shoot_report.get("qa_pass", False))
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
            "quality_qa_pass": quality_report.get("qa_pass"),
            "events_removed_vs_baseline": (quality_report.get("delta_vs_baseline") or {}).get(
                "events_removed"
            ),
            "packs": {
                "qa_pass": pack_report.get("qa_pass"),
                "today": pack_report.get("today"),
                "tomorrow": pack_report.get("tomorrow"),
            },
            "viral_recurrence": {
                "qa_pass": viral_report.get("qa_pass"),
                "match_count": viral_report.get("match_count"),
                "label_counts": viral_report.get("label_counts"),
                "next_14d_crowd_magnets": viral_report.get("next_14d_crowd_magnets"),
                "historical_rows": hist_report.get("compact_row_count"),
            },
            "parade_census": {
                "qa_pass": parade_census_report.get("qa_pass"),
                "anchor_count": parade_census_report.get("anchor_count"),
                "permit_extracted_count": parade_census_report.get("permit_extracted_count"),
                "merged_total": parade_census_report.get("merged_total"),
                "anchor_permit_matches": parade_census_report.get("anchor_permit_matches"),
                "report": "data/citywide_parade_census_report.json",
            },
            "news_desk_checklist": {
                "qa_pass": news_desk_report.get("qa_pass"),
                "total_rows": news_desk_report.get("total_rows"),
                "today_count": news_desk_report.get("today_count"),
                "priority_unchecked_count": news_desk_report.get("priority_unchecked_count"),
                "map_ready_count": news_desk_report.get("map_ready_count"),
                "artifact": "data/news_desk_assignment_checklist.json",
                "csv": "data/news_desk_assignment_checklist.csv",
            },
            "pin_integrity": {
                "qa_pass": pin_report.get("qa_pass"),
                "demotion_count": pin_report.get("demotion_count"),
                "map_ready_before_total": pin_report.get("map_ready_before_total"),
                "map_ready_after_total": pin_report.get("map_ready_after_total"),
                "demotion_reason_counts": pin_report.get("demotion_reason_counts"),
                "report": "data/pin_integrity_gate_report.json",
            },
            "shoot_day_certified": {
                "qa_pass": shoot_report.get("qa_pass"),
                "today_certified_pins": shoot_report.get("today_certified_pins"),
                "tomorrow_certified_pins": shoot_report.get("tomorrow_certified_pins"),
                "pack": "data/photographer_shoot_day_certified_pack.json",
            },
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": (
            "Safe daily desk sync. Does not run build_staged_production_feed / "
            "build_location_cache / public WordPress publish. Pin integrity gate "
            "fail-closed: qa_pass requires ZERO bad map_ready pins. Full permit→staged "
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
