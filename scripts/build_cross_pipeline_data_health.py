#!/usr/bin/env python3
"""Build the NYC/NJ cross-pipeline location-accounting health contract.

All production file access is bound to fixed repository constants. Reusable
logic accepts parsed event objects, never filesystem paths. The NJ workflow must
place its reviewed handoff at ``data/external/nj_events.json`` before production
integration is authorized.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cross_pipeline_health import account_pipeline, delta, event_rows

ROOT = Path(__file__).resolve().parents[1]
NYC_STAGED = ROOT / "data" / "events_schema_v1_staged.json"
NYC_SUPPLEMENTAL = ROOT / "data" / "events_schema_v1_supplemental_review.json"
NJ_INPUT = ROOT / "data" / "external" / "nj_events.json"
DAILY_HEALTH = ROOT / "status" / "nycif-daily-data-health.json"
OUTPUT = ROOT / "status" / "nycif-cross-pipeline-location-health.json"

NYC_INPUT_LABELS = (
    "data/events_schema_v1_staged.json",
    "data/events_schema_v1_supplemental_review.json",
)
NJ_INPUT_LABEL = "data/external/nj_events.json"
OUTPUT_LABEL = "status/nycif-cross-pipeline-location-health.json"
DAILY_HEALTH_LABEL = "status/nycif-daily-data-health.json"


def _parse_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_nyc_staged() -> dict[str, Any]:
    try:
        return _parse_object(NYC_STAGED.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_nyc_supplemental() -> dict[str, Any]:
    try:
        return _parse_object(NYC_SUPPLEMENTAL.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_nj_handoff() -> dict[str, Any]:
    try:
        return _parse_object(NJ_INPUT.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_previous_output() -> dict[str, Any]:
    try:
        return _parse_object(OUTPUT.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_daily_health() -> dict[str, Any]:
    try:
        return _parse_object(DAILY_HEALTH.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _write_output(report: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_daily_health(report: dict[str, Any]) -> None:
    DAILY_HEALTH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def blocker(code: str, message: str, artifact: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "critical",
        "message": message,
        "artifact": artifact,
    }


def build_report(
    *,
    nyc_events: list[dict[str, Any]],
    nj_events: list[dict[str, Any]],
    missing_nyc_inputs: list[str] | None = None,
    missing_nj_input: bool = False,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the invariant report from parsed event records only."""
    nyc = account_pipeline("nyc", nyc_events)
    nj = account_pipeline("nj", nj_events)

    prior_pipelines = previous.get("pipelines") if isinstance(previous, dict) else {}
    nyc["daily_delta"] = delta(
        nyc,
        prior_pipelines.get("nyc") if isinstance(prior_pipelines, dict) else None,
    )
    nj["daily_delta"] = delta(
        nj,
        prior_pipelines.get("nj") if isinstance(prior_pipelines, dict) else None,
    )

    blockers: list[dict[str, str]] = []
    for label in missing_nyc_inputs or []:
        blockers.append(
            blocker(
                "NYC_LOCATION_INPUT_MISSING",
                "NYC location-accounting input is missing or unreadable.",
                label,
            )
        )
    if missing_nj_input:
        blockers.append(
            blocker(
                "NJ_LOCATION_INPUT_MISSING",
                "NJ cross-repository artifact handoff is missing or unreadable.",
                NJ_INPUT_LABEL,
            )
        )
    if nyc["unaccounted_count"]:
        blockers.append(
            blocker(
                "NYC_UNACCOUNTED_LOCATION_RECORDS",
                f"NYC has {nyc['unaccounted_count']} records without a recognized disposition.",
                ",".join(NYC_INPUT_LABELS),
            )
        )
    if nj["unaccounted_count"]:
        blockers.append(
            blocker(
                "NJ_UNACCOUNTED_LOCATION_RECORDS",
                f"NJ has {nj['unaccounted_count']} records without a recognized disposition.",
                NJ_INPUT_LABEL,
            )
        )

    qa_pass = not blockers and nyc["qa_pass"] and nj["qa_pass"]
    return {
        "schema_version": "1.0",
        "status": "READY" if qa_pass else "BLOCKED",
        "qa_pass": qa_pass,
        "publication_allowed": qa_pass,
        "required_invariant": (
            "map_safe_count + approximate_count + list_only_count = total_count"
        ),
        "inputs": {
            "nyc": list(NYC_INPUT_LABELS),
            "nj": [NJ_INPUT_LABEL],
            "nyc_missing": list(missing_nyc_inputs or []),
            "nj_missing": [NJ_INPUT_LABEL] if missing_nj_input else [],
        },
        "pipelines": {"nyc": nyc, "nj": nj},
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def apply_cross_to_daily(
    daily: dict[str, Any], cross: dict[str, Any]
) -> dict[str, Any]:
    """Purely combine daily and cross-pipeline health objects."""
    combined = dict(daily)
    combined["cross_pipeline_health"] = cross
    if not cross.get("qa_pass"):
        combined["status"] = "BLOCKED"
        combined["release_ready"] = False
        combined["publication_allowed"] = False
        existing = combined.get("blockers")
        blockers = list(existing) if isinstance(existing, list) else []
        blockers.extend(cross.get("blockers") or [])
        combined["blockers"] = blockers
    return combined


def build_fixed_report() -> dict[str, Any]:
    staged = _read_nyc_staged()
    supplemental = _read_nyc_supplemental()
    nj_payload = _read_nj_handoff()
    missing_nyc: list[str] = []
    if not staged:
        missing_nyc.append(NYC_INPUT_LABELS[0])
    if not supplemental:
        missing_nyc.append(NYC_INPUT_LABELS[1])
    return build_report(
        nyc_events=event_rows(staged) + event_rows(supplemental),
        nj_events=event_rows(nj_payload),
        missing_nyc_inputs=missing_nyc,
        missing_nj_input=not bool(nj_payload),
        previous=_read_previous_output(),
    )


def run_fixed_contract(*, augment: bool = False) -> dict[str, Any]:
    report = build_fixed_report()
    _write_output(report)
    if not augment:
        return report

    daily = _read_daily_health()
    if not daily:
        report["status"] = "BLOCKED"
        report["qa_pass"] = False
        report["publication_allowed"] = False
        report["blockers"].append(
            blocker(
                "DAILY_HEALTH_AUGMENT_FAILED",
                "Daily health report is missing or unreadable.",
                DAILY_HEALTH_LABEL,
            )
        )
        report["blocker_count"] = len(report["blockers"])
        _write_output(report)
        return report

    _write_daily_health(apply_cross_to_daily(daily, report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--augment-daily-health", action="store_true")
    args = parser.parse_args(argv)
    report = run_fixed_contract(augment=bool(args.augment_daily_health))
    print(
        json.dumps(
            {
                "status": report["status"],
                "qa_pass": report["qa_pass"],
                "nyc": report["pipelines"]["nyc"],
                "nj": report["pipelines"]["nj"],
                "output": OUTPUT_LABEL,
                "daily_health_augmented": bool(args.augment_daily_health),
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
