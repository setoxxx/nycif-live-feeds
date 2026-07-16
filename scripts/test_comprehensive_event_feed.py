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


def test_built_artifact_invariants() -> None:
    feed_path = ROOT / "data" / "schema-v1-discovery" / "all" / "events.json"
    if not feed_path.exists():
        print("  (skip) comprehensive feed not built yet")
        return
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    events = feed["events"]

    ids = [e["id"] for e in events]
    if len(ids) != len(set(ids)):
        fail("comprehensive feed has duplicate event ids")

    for e in events:
        if e["category"] not in ALLOWED:
            fail(f"event {e['id']} has category {e['category']!r} outside taxonomy")
        status = e["nycif"]["coordinate_status"]
        if status == "map_ready":
            if not mod.valid_coord(e["latitude"], e["longitude"]):
                fail(f"map_ready event {e['id']} has an uncertified coord")
        elif status == "list_only":
            if e["latitude"] is not None or e["longitude"] is not None:
                fail(f"list_only event {e['id']} still carries coordinates")
        else:
            fail(f"event {e['id']} has unexpected coordinate_status {status!r}")
        # is_past must agree with end_date < today window snapshot
        if e["is_past"] and e["end_date"] >= feed["window"]["today"]:
            fail(f"event {e['id']} flagged past but ends today/future")

    if feed["map_ready"] < 1:
        fail("comprehensive feed has no map-ready events")
    print(f"  artifact ok: {feed['total']} events, {feed['map_ready']} map_ready, "
          f"{len(feed['category_counts'])} categories, "
          f"{feed['new_this_run']} new this run")


def main() -> int:
    tests = [
        test_every_nyc_type_maps_to_a_valid_category,
        test_media_lane_covers_production_family,
        test_coordinate_certification,
        test_built_artifact_invariants,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("All comprehensive-feed tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
