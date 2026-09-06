#!/usr/bin/env python3
"""One-shot / replay: pull Culture help-calendar + civic sources, then load.

Uses existing pullers. Live SODA when asked; fixture fallback when --live
exits 2/3 or fails. Does not invent events. Does not flip publication gates.
Default is pull + dry-run load. Pass --write to upsert into the approved
Supabase project (oggwpvdirkrnzoolparx).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.common import REPORT_DIR  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "culture"
PYTHON = sys.executable

CALENDAR_STEPS = (
    (
        "workforce1",
        [str(ROOT / "scripts/culture/pull_workforce1_events.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_workforce1_events.py"), "--fixture", str(FIXTURES / "workforce1_events.fixture.json")],
    ),
    (
        "dol",
        [str(ROOT / "scripts/culture/pull_dol_career_events.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_dol_career_events.py"), "--fixture", str(FIXTURES / "dol_career_events.fixture.json")],
    ),
    (
        "cuny",
        [str(ROOT / "scripts/culture/pull_cuny_career_events.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_cuny_career_events.py")],
    ),
    (
        "nybc",
        [str(ROOT / "scripts/culture/pull_nybc_blood_drives.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_nybc_blood_drives.py"), "--fixture", str(FIXTURES / "nybc_blood_drives.fixture.json")],
    ),
    (
        "show",
        [str(ROOT / "scripts/culture/pull_show_mobile_clinics.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_show_mobile_clinics.py"), "--fixture", str(FIXTURES / "show_mobile_clinics.fixture.json")],
    ),
    (
        "aspca",
        [str(ROOT / "scripts/culture/pull_aspca_mobile.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_aspca_mobile.py"), "--fixture", str(FIXTURES / "aspca_mobile.fixture.json")],
    ),
)

CIVIC_STEPS = (
    (
        "nypd",
        [str(ROOT / "scripts/culture/pull_nypd_precincts.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_nypd_precincts.py"), "--fixture", str(FIXTURES / "nypd_precincts.fixture.json")],
    ),
    (
        "fdny",
        [str(ROOT / "scripts/culture/pull_fdny_firehouses.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_fdny_firehouses.py"), "--fixture", str(FIXTURES / "fdny_firehouses.fixture.json")],
    ),
    (
        "shelters",
        [str(ROOT / "scripts/culture/pull_shelters.py"), "--live"],
        [str(ROOT / "scripts/culture/pull_shelters.py"), "--fixture", str(FIXTURES / "shelters_census_only.fixture.json")],
    ),
)


def _run(label: str, live_cmd: list[str], fallback_cmd: list[str], *, fixture_only: bool) -> str:
    if fixture_only:
        completed = subprocess.run([PYTHON, *fallback_cmd], cwd=ROOT)
        if completed.returncode != 0:
            raise SystemExit(f"{label} fixture pull failed with {completed.returncode}")
        return "fixture"
    completed = subprocess.run([PYTHON, *live_cmd], cwd=ROOT)
    if completed.returncode == 0:
        return "live"
    if completed.returncode in {2, 3}:
        print(f"{label} live not wired (exit {completed.returncode}); using fixture/registry, inventing nothing")
        fallback = subprocess.run([PYTHON, *fallback_cmd], cwd=ROOT)
        if fallback.returncode != 0:
            raise SystemExit(f"{label} fixture fallback failed with {fallback.returncode}")
        return "fixture_fallback"
    raise SystemExit(f"{label} unexpected exit {completed.returncode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("calendar", "civic", "all"), default="all")
    parser.add_argument("--fixture-only", action="store_true", help="Skip live SODA; use committed fixtures")
    parser.add_argument("--write", action="store_true", help="Pass --write through to the loader")
    parser.add_argument("--skip-pull", action="store_true", help="Load whatever is already in staging/")
    parser.add_argument("--emit-sql", type=Path, help="Forward to the loader")
    args = parser.parse_args(argv)

    sources_used: dict[str, str] = {}
    if not args.skip_pull:
        if args.dataset in {"calendar", "all"}:
            for label, live_cmd, fallback_cmd in CALENDAR_STEPS:
                sources_used[label] = _run(label, live_cmd, fallback_cmd, fixture_only=args.fixture_only)
        if args.dataset in {"civic", "all"}:
            for label, live_cmd, fallback_cmd in CIVIC_STEPS:
                sources_used[label] = _run(label, live_cmd, fallback_cmd, fixture_only=args.fixture_only)
        validate = subprocess.run(
            [PYTHON, str(ROOT / "scripts/culture/validate_before_publish.py")],
            cwd=ROOT,
        )
        if validate.returncode != 0:
            raise SystemExit("validate_before_publish failed; refusing load")

    load_cmd = [
        PYTHON,
        str(ROOT / "scripts/culture/load_calendar_civic_staging.py"),
        "--dataset",
        args.dataset,
    ]
    if args.write:
        load_cmd.append("--write")
    if args.emit_sql:
        load_cmd.extend(["--emit-sql", str(args.emit_sql)])
    loaded = subprocess.run(load_cmd, cwd=ROOT)
    report_path = REPORT_DIR / "calendar_civic_backfill_sources.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        __import__("json").dumps(
            {
                "sources_used": sources_used,
                "dataset": args.dataset,
                "write": args.write,
                "publication_allowed": False,
                "gates_touched": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return loaded.returncode


if __name__ == "__main__":
    raise SystemExit(main())
