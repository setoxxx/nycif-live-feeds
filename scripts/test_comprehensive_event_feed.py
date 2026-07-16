#!/usr/bin/env python3
"""Automated QA for the comprehensive "100% of the city" event feed builder.

Hermetic checks on the pure logic (category mapping, coordinate certification)
plus invariant checks on the built artifact when it is present.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from schema_v1_common import VALID_CATEGORIES  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "build_comprehensive_event_feed",
    ROOT / "scripts" / "build_comprehensive_event_feed.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# The "media" lane (production/film/press) is the one category the comprehensive
# feed adds on top of the base taxonomy.
ALLOWED = set(VALID_CATEGORIES) | {"media"}

# Every permit type NYC publishes (the list the operator pasted from the city).
NYC_PERMIT_TYPES = [
    "Open Culture", "Athletic-Charitable", "Athletic Race/Tour", "Block Party",
    "Clean-up", "Concert", "DCAS Prep/Shoot/Wrap Permit", "Farmers Market",
    "Health Fair", "Marathon", "Miscellaneous", "Mobile Unit", "Parade",
    "Plaza Event", "Plaza Partner Event", "Play Streets", "Press Conference",
    "Production Event", "Public Program/Exhibitions", "Rally", "Red Carpet Event",
    "Religious Event", "Rigging Permit", "Shooting Permit", "Sidewalk Sale",
    "Single Block Festival", "Special Event", "Stationary Demonstration",
    "Street Event", "Street Festival", "Theater load in and load outs",
]


def fail(msg: str) -> None:
    raise AssertionError(msg)


def test_every_nyc_type_maps_to_a_valid_category() -> None:
    for t in NYC_PERMIT_TYPES:
        cat = mod.category_for({"event_type": t})
        if cat not in ALLOWED:
            fail(f"NYC type {t!r} -> {cat!r} not in allowed categories")
    # Nothing is ever orphaned: an unknown type falls back to the row's own
    # category, then "general".
    if mod.category_for({"event_type": "Totally Unknown Type"}) != "general":
        fail("unknown type without a row category should fall back to general")
    if mod.category_for({"event_type": "Nope", "category": "arts"}) != "arts":
        fail("unknown type should fall back to the row's own category")


def test_media_lane_covers_production_family() -> None:
    for t in ["Production Event", "Shooting Permit", "Press Conference",
              "Red Carpet Event", "Rigging Permit",
              "Theater load in and load outs", "DCAS Prep/Shoot/Wrap Permit"]:
        if mod.category_for({"event_type": t}) != "media":
            fail(f"{t!r} should map to the media lane")


def test_coordinate_certification() -> None:
    if not mod.valid_coord(40.7128, -74.0060):  # Manhattan
        fail("valid NYC coord rejected")
    if mod.valid_coord(0, 0):  # null island
        fail("null island accepted")
    if mod.valid_coord(40.7128, -60.0):  # Atlantic
        fail("out-of-box (ocean) coord accepted")
    if mod.valid_coord(None, None):
        fail("missing coords accepted")


def test_built_artifacts() -> None:
    report_path = ROOT / "data" / "comprehensive_feed_report.json"
    new_path = ROOT / "data" / "nycif_new_events.json"
    if not report_path.exists() or not new_path.exists():
        print("  (skip) artifacts not built yet")
        return
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    nw = json.loads(new_path.read_text(encoding="utf-8"))

    # every category in the coverage report is a real taxonomy slug
    for cat in rep["category_coverage"]:
        if cat not in ALLOWED:
            fail(f"coverage lists category {cat!r} outside taxonomy")
    # every NYC type present routes to the category its coverage claims
    for cat, info in rep["category_coverage"].items():
        for etype in info["event_types"]:
            if mod.category_for({"event_type": etype}) != cat:
                fail(f"coverage puts {etype!r} under {cat!r} but it maps elsewhere")
    if rep["map_ready"] < 1 or not rep["qa_pass"]:
        fail("coverage report has no map-ready events / failed QA")
    # What's-New diff shape
    for e in nw["events"]:
        if e["id"].count("@") != 1:
            fail(f"new event id {e['id']!r} is not per-day-instance keyed")
    print(f"  artifacts ok: {rep['kept']} scanned, {rep['map_ready']} map_ready, "
          f"{len(rep['category_counts'])} categories with data, "
          f"{nw['new_this_run']} new this run")


def main() -> int:
    tests = [
        test_every_nyc_type_maps_to_a_valid_category,
        test_media_lane_covers_production_family,
        test_coordinate_certification,
        test_built_artifacts,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("All comprehensive-feed tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
