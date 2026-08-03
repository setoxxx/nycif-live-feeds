#!/usr/bin/env python3
"""Build legacy launch health plus mandatory NYC/NJ location accounting.

The existing production health implementation is preserved in
``build_daily_data_health_legacy``. This public entrypoint runs that contract,
then adds a cross-pipeline invariant:

``map_safe_count + approximate_count + list_only_count == total_count``

for both NYC and NJ. Missing NJ artifact handoff, unknown disposition values, or
any unaccounted record blocks the final health result.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import build_daily_data_health_legacy as legacy
from cross_pipeline_health import account_pipeline, delta, load_events

# Preserve the complete import surface used by existing regression tests and
# production helpers. The wrapper's definitions below intentionally replace
# only its execution entrypoint and cross-pipeline support functions.
for _legacy_name in dir(legacy):
    if not _legacy_name.startswith("__"):
        globals().setdefault(_legacy_name, getattr(legacy, _legacy_name))

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NYC_INPUTS = (
    ROOT / "data" / "events_schema_v1_staged.json",
    ROOT / "data" / "events_schema_v1_supplemental_review.json",
)
DEFAULT_NJ_INPUT = ROOT / "data" / "external" / "nj_events.json"


def load_json(path: Path) -> dict[str, Any]:
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


def existing_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    value = report.get("blockers")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if value:
        report["legacy_blockers"] = value
    return []


def build_cross_section(
    *,
    nyc_paths: list[Path],
    nj_paths: list[Path],
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    nyc_events, nyc_missing = load_events(nyc_paths)
    nj_events, nj_missing = load_events(nj_paths)
    nyc = account_pipeline("nyc", nyc_events)
    nj = account_pipeline("nj", nj_events)

    prior_cross = previous.get("cross_pipeline_health") if isinstance(previous, dict) else {}
    prior_pipelines = prior_cross.get("pipelines") if isinstance(prior_cross, dict) else {}
    nyc["daily_delta"] = delta(nyc, prior_pipelines.get("nyc") if isinstance(prior_pipelines, dict) else None)
    nj["daily_delta"] = delta(nj, prior_pipelines.get("nj") if isinstance(prior_pipelines, dict) else None)

    blockers: list[dict[str, str]] = []
    for path in nyc_missing:
        blockers.append(blocker("NYC_LOCATION_INPUT_MISSING", "NYC location-accounting input is missing or unreadable.", path))
    for path in nj_missing:
        blockers.append(blocker("NJ_LOCATION_INPUT_MISSING", "NJ cross-repository artifact handoff is missing or unreadable.", path))
    if nyc["unaccounted_count"]:
        blockers.append(blocker("NYC_UNACCOUNTED_LOCATION_RECORDS", f"NYC has {nyc['unaccounted_count']} records without a recognized disposition.", ",".join(str(path) for path in nyc_paths)))
    if nj["unaccounted_count"]:
        blockers.append(blocker("NJ_UNACCOUNTED_LOCATION_RECORDS", f"NJ has {nj['unaccounted_count']} records without a recognized disposition.", ",".join(str(path) for path in nj_paths)))

    section = {
        "schema_version": "1.0",
        "qa_pass": not blockers and nyc["qa_pass"] and nj["qa_pass"],
        "required_invariant": "map_safe_count + approximate_count + list_only_count = total_count",
        "inputs": {
            "nyc": [str(path) for path in nyc_paths],
            "nj": [str(path) for path in nj_paths],
            "nyc_missing": nyc_missing,
            "nj_missing": nj_missing,
        },
        "pipelines": {"nyc": nyc, "nj": nj},
        "blocker_count": len(blockers),
        "publication_allowed": False if blockers else True,
    }
    return section, blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-only", action="store_true", help="Run only the NYC/NJ accounting layer.")
    parser.add_argument("--nyc-input", action="append")
    parser.add_argument("--nj-input", action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    output = args.output or legacy.OUT
    previous = load_json(output)
    legacy_rc = 0
    if args.cross_only:
        report: dict[str, Any] = {
            "schema_version": "cross-pipeline-test-1.0",
            "status": "READY",
            "blockers": [],
        }
    else:
        legacy_rc = int(legacy.main() or 0)
        report = load_json(legacy.OUT)
        if not report:
            report = {"status": "BLOCKED", "blockers": []}

    nyc_paths, nj_paths = resolve_inputs(args)
    cross, cross_blockers = build_cross_section(
        nyc_paths=nyc_paths,
        nj_paths=nj_paths,
        previous=previous,
    )
    report["cross_pipeline_health"] = cross
    blockers = existing_blockers(report)
    blockers.extend(cross_blockers)
    report["blockers"] = blockers

    if legacy_rc != 0 or not cross["qa_pass"]:
        report["status"] = "BLOCKED"
        report["qa_pass"] = False
        report["publication_allowed"] = False
    else:
        report["qa_pass"] = bool(report.get("qa_pass", True))
        if report.get("status") not in {"BLOCKED", "ERROR"}:
            report["status"] = "READY"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "legacy_exit": legacy_rc,
                "cross_pipeline_qa_pass": cross["qa_pass"],
                "nyc": cross["pipelines"]["nyc"],
                "nj": cross["pipelines"]["nj"],
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0 if legacy_rc == 0 and cross["qa_pass"] and report.get("status") != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
