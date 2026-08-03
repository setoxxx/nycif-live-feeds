#!/usr/bin/env python3
"""Build the NYC/NJ cross-pipeline location-accounting health contract.

This is a companion to ``build_daily_data_health.py``. It does not replace or
change the proven NYC production-health implementation. Production integration
requires an explicit NJ artifact handoff and separate approval.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from cross_pipeline_health import account_pipeline, delta, load_events

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NYC_INPUTS = (
    ROOT / "data" / "events_schema_v1_staged.json",
    ROOT / "data" / "events_schema_v1_supplemental_review.json",
)
DEFAULT_NJ_INPUT = ROOT / "data" / "external" / "nj_events.json"
DEFAULT_DAILY_HEALTH = ROOT / "status" / "nycif-daily-data-health.json"
DEFAULT_OUTPUT = ROOT / "status" / "nycif-cross-pipeline-location-health.json"


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def split_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(part).expanduser() for part in value.split(os.pathsep) if part.strip()]


def resolve_inputs(args: argparse.Namespace) -> tuple[list[Path], list[Path]]:
    nyc = [Path(value) for value in (args.nyc_input or [])]
    if not nyc:
        nyc = split_paths(os.environ.get("NYCIF_NYC_HEALTH_INPUTS"))
    if not nyc:
        nyc = list(DEFAULT_NYC_INPUTS)

    nj = [Path(value) for value in (args.nj_input or [])]
    if not nj:
        nj = split_paths(os.environ.get("NYCIF_NJ_HEALTH_INPUT"))
    if not nj:
        nj = [DEFAULT_NJ_INPUT]
    return nyc, nj


def blocker(code: str, message: str, artifact: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "critical",
        "message": message,
        "artifact": artifact,
    }


def build_report(
    *,
    nyc_paths: list[Path],
    nj_paths: list[Path],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nyc_events, nyc_missing = load_events(nyc_paths)
    nj_events, nj_missing = load_events(nj_paths)
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
    for missing in nyc_missing:
        blockers.append(
            blocker(
                "NYC_LOCATION_INPUT_MISSING",
                "NYC location-accounting input is missing or unreadable.",
                missing,
            )
        )
    for missing in nj_missing:
        blockers.append(
            blocker(
                "NJ_LOCATION_INPUT_MISSING",
                "NJ cross-repository artifact handoff is missing or unreadable.",
                missing,
            )
        )
    if nyc["unaccounted_count"]:
        blockers.append(
            blocker(
                "NYC_UNACCOUNTED_LOCATION_RECORDS",
                f"NYC has {nyc['unaccounted_count']} records without a recognized disposition.",
                ",".join(str(path) for path in nyc_paths),
            )
        )
    if nj["unaccounted_count"]:
        blockers.append(
            blocker(
                "NJ_UNACCOUNTED_LOCATION_RECORDS",
                f"NJ has {nj['unaccounted_count']} records without a recognized disposition.",
                ",".join(str(path) for path in nj_paths),
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
            "nyc": [str(path) for path in nyc_paths],
            "nj": [str(path) for path in nj_paths],
            "nyc_missing": nyc_missing,
            "nj_missing": nj_missing,
        },
        "pipelines": {"nyc": nyc, "nj": nj},
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def augment_daily_health(path: Path, cross: dict[str, Any]) -> None:
    """Add the cross-pipeline section only when explicitly requested."""
    daily = load_object(path)
    if not daily:
        raise FileNotFoundError(f"daily health report is missing or unreadable: {path}")
    daily["cross_pipeline_health"] = cross
    if not cross.get("qa_pass"):
        daily["status"] = "BLOCKED"
        daily["release_ready"] = False
        daily["publication_allowed"] = False
        existing = daily.get("blockers")
        blockers = existing if isinstance(existing, list) else []
        blockers.extend(cross.get("blockers") or [])
        daily["blockers"] = blockers
    path.write_text(json.dumps(daily, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nyc-input", action="append")
    parser.add_argument("--nj-input", action="append")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--daily-health", type=Path, default=DEFAULT_DAILY_HEALTH)
    parser.add_argument("--augment-daily-health", action="store_true")
    args = parser.parse_args(argv)

    previous = load_object(args.output)
    nyc_paths, nj_paths = resolve_inputs(args)
    report = build_report(
        nyc_paths=nyc_paths,
        nj_paths=nj_paths,
        previous=previous,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.augment_daily_health:
        try:
            augment_daily_health(args.daily_health, report)
        except (OSError, ValueError) as exc:
            report["status"] = "BLOCKED"
            report["qa_pass"] = False
            report["publication_allowed"] = False
            report["blockers"].append(
                blocker("DAILY_HEALTH_AUGMENT_FAILED", str(exc), str(args.daily_health))
            )
            report["blocker_count"] = len(report["blockers"])
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    print(
        json.dumps(
            {
                "status": report["status"],
                "qa_pass": report["qa_pass"],
                "nyc": report["pipelines"]["nyc"],
                "nj": report["pipelines"]["nj"],
                "output": str(args.output),
                "daily_health_augmented": bool(args.augment_daily_health),
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
