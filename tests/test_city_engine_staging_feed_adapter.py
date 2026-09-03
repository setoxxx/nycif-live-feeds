#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_city_engine_staging_feed.py"
PARENT_ID = "nyc_open_data:tvpp-9vvx:trans-latina-2026"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def event(**overrides):
    base = {
        "id": PARENT_ID,
        "title": "15th Annual Trans Latina March",
        "date": "2026-07-27",
        "start_date_time": "2026-07-27T17:00:00.000",
        "end_date_time": "2026-07-27T21:00:00.000",
        "borough": "Queens",
        "category": "march",
        "display_location": "Jackson Heights, Queens",
        "lat": 40.7557,
        "lng": -73.8831,
        "event_agency": "Street Activity Permit Office",
        "event_type": "Street Event",
        "source_dataset": "tvpp-9vvx",
        "source_event_id": "trans-latina-2026",
        "staged_feed": True,
        "production_ready": True,
        "needs_review": False,
    }
    base.update(overrides)
    return base


def run_adapter(events, *, generated_at="2026-07-27T12:00:00+00:00", reviewed_at="2026-07-27T16:00:00+00:00"):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    input_path = root / "staged.json"
    metadata_path = root / "metadata.json"
    output_dir = root / "out"
    write_json(input_path, {"events": events})
    write_json(metadata_path, {"generated_at_utc": generated_at})
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input", str(input_path),
            "--metadata", str(metadata_path),
            "--output-dir", str(output_dir),
            "--window-start", "2026-07-27",
            "--window-days", "8",
            "--reviewed-at", reviewed_at,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return temp, root, output_dir, result


def load_output(output_dir: Path):
    feed = json.loads((output_dir / "city-engine-staging-feed.geojson").read_text())
    report = json.loads((output_dir / "city-engine-staging-feed-report.json").read_text())
    return feed, report


def test_builds_protected_feed_and_excludes_ineligible_rows():
    temp, root, output_dir, result = run_adapter([
        event(),
        event(id="review-row", needs_review=True),
        event(id="past-row", date="2026-07-20"),
    ])
    try:
        assert result.returncode == 0, result.stderr
        feed, report = load_output(output_dir)
        assert [feature["properties"]["title"] for feature in feed["features"]] == ["15th Annual Trans Latina March"]
        properties = feed["features"][0]["properties"]
        assert properties["event_id"] == PARENT_ID
        assert properties["source_parent_event_id"] == PARENT_ID
        assert properties["borough"] == "Queens"
        assert properties["category"] == "Parade / March / Procession"
        assert properties["public_display_eligible"] is False
        assert properties["staging_display_eligible"] is True
        assert report["counts"]["included"] == 1
        assert report["counts"]["needs_review"] == 1
        assert report["counts"]["outside_window"] == 1
        assert report["counts"]["derived_occurrence_ids"] == 0
        assert report["ready_for_protected_staging"] is True
    finally:
        temp.cleanup()


def test_equivalent_duplicate_rows_collapse_to_one_feature():
    temp, root, output_dir, result = run_adapter([event(), event()])
    try:
        assert result.returncode == 0, result.stderr
        feed, report = load_output(output_dir)
        assert len(feed["features"]) == 1
        assert feed["features"][0]["properties"]["event_id"] == PARENT_ID
        assert report["counts"]["included"] == 1
        assert report["counts"]["equivalent_duplicates_collapsed"] == 1
        assert report["counts"]["multi_occurrence_source_ids"] == 0
        assert report["counts"]["identity_collisions"] == 0
        assert report["ready_for_protected_staging"] is True
    finally:
        temp.cleanup()


def test_distinct_occurrences_receive_stable_derived_ids():
    first = event()
    second = event(
        date="2026-07-28",
        start_date_time="2026-07-28T18:00:00.000",
        end_date_time="2026-07-28T20:00:00.000",
        display_location="Flushing Meadows Corona Park",
        lat=40.7498,
        lng=-73.8408,
    )

    temp_a, root_a, output_a, result_a = run_adapter([first, second])
    temp_b, root_b, output_b, result_b = run_adapter([second, first])
    try:
        assert result_a.returncode == 0, result_a.stderr
        assert result_b.returncode == 0, result_b.stderr
        feed_a, report_a = load_output(output_a)
        feed_b, report_b = load_output(output_b)

        ids_a = [feature["properties"]["event_id"] for feature in feed_a["features"]]
        ids_b = [feature["properties"]["event_id"] for feature in feed_b["features"]]
        assert ids_a == ids_b
        assert len(ids_a) == 2
        assert len(set(ids_a)) == 2
        assert all(event_id.startswith(f"{PARENT_ID}:occ:") for event_id in ids_a)
        assert all(len(event_id.rsplit(":", 1)[1]) == 20 for event_id in ids_a)
        assert all(
            feature["properties"]["source_parent_event_id"] == PARENT_ID
            for feature in feed_a["features"]
        )
        assert report_a["counts"]["multi_occurrence_source_ids"] == 1
        assert report_a["counts"]["derived_occurrence_ids"] == 2
        assert report_a["counts"]["identity_collisions"] == 0
        assert report_b["counts"] == report_a["counts"]
        assert report_a["ready_for_protected_staging"] is True
    finally:
        temp_a.cleanup()
        temp_b.cleanup()


def test_subsecond_clock_skew_does_not_mark_source_stale():
    temp, root, output_dir, result = run_adapter(
        [event()],
        generated_at="2026-09-03T20:59:47.326624+00:00",
        reviewed_at="2026-09-03T20:59:47+00:00",
    )
    try:
        assert result.returncode == 0, result.stderr
        report = json.loads((output_dir / "city-engine-staging-feed-report.json").read_text())
        assert report["source_fresh"] is True
        assert report["ready_for_protected_staging"] is True
        assert "source feed is stale" not in report["blocking_reasons"]
        assert report["source_age_hours"] == 0.0
    finally:
        temp.cleanup()


def test_stale_source_writes_report_but_not_feed():
    temp, root, output_dir, result = run_adapter(
        [event()],
        generated_at="2026-07-14T01:52:03+00:00",
        reviewed_at="2026-07-27T16:00:00+00:00",
    )
    try:
        assert result.returncode == 2
        report = json.loads((output_dir / "city-engine-staging-feed-report.json").read_text())
        assert report["source_fresh"] is False
        assert report["ready_for_protected_staging"] is False
        assert "source feed is stale" in report["blocking_reasons"]
        assert not (output_dir / "city-engine-staging-feed.geojson").exists()
    finally:
        temp.cleanup()


if __name__ == "__main__":
    test_builds_protected_feed_and_excludes_ineligible_rows()
    test_equivalent_duplicate_rows_collapse_to_one_feature()
    test_distinct_occurrences_receive_stable_derived_ids()
    test_subsecond_clock_skew_does_not_mark_source_stale()
    test_stale_source_writes_report_but_not_feed()
    print("City Engine protected staging feed adapter tests passed.")
