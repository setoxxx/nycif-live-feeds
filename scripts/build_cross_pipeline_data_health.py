#!/usr/bin/env python3
"""Build the NYC/NJ cross-pipeline location-accounting health contract.

This companion command uses fixed repository artifact paths. It does not accept
operator-controlled filesystem paths and does not replace the proven NYC daily
health implementation. The NJ workflow must place its reviewed handoff at
``data/external/nj_events.json`` before production integration is authorized.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cross_pipeline_health import account_pipeline, delta, load_events

ROOT = Path(__file__).resolve().parents[1]
NYC_INPUTS = (
    ROOT / "data" / "events_schema_v1_staged.json",
    ROOT / "data" / "events_schema_v1_supplemental_review.json",
)
NJ_INPUT = ROOT / "data" / "external" / "nj_events.json"
DAILY_HEALTH = ROOT / "status" / "nycif-daily-data-health.json"
OUTPUT = ROOT / "status" / "nycif-cross-pipeline-location-health.json"


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
            "nyc": [str(path.relative_to(ROOT)) for path in nyc_paths],
            "nj": [str(path.relative_to(ROOT)) for path in nj_paths],
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


def run_fixed_contract(*, augment: bool = False) -> dict[str, Any]:
    previous = load_object(OUTPUT)
    report = build_report(
        nyc_paths=list(NYC_INPUTS),
        nj_paths=[NJ_INPUT],
        previous=previous,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if augment:
        try:
            augment_daily_health(DAILY_HEALTH, report)
        except (OSError, ValueError) as exc:
            report["status"] = "BLOCKED"
            report["qa_pass"] = False
            report["publication_allowed"] = False
            report["blockers"].append(
                blocker("DAILY_HEALTH_AUGMENT_FAILED", str(exc), str(DAILY_HEALTH.relative_to(ROOT)))
            )
            report["blocker_count"] = len(report["blockers"])
            OUTPUT.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
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
                "output": str(OUTPUT.relative_to(ROOT)),
                "daily_health_augmented": bool(args.augment_daily_health),
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
