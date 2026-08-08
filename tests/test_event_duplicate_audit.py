import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_event_duplicate_candidates.py"
spec = importlib.util.spec_from_file_location("event_duplicate_audit", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def event(event_id, title, *, date="2026-08-08", start="2026-08-08T12:00:00-04:00", borough="Brooklyn", location="Marine Park", dataset="source-a", source_id="1"):
    return {
        "id": event_id,
        "title": title,
        "start_date_time": start,
        "borough": borough,
        "location": location,
        "event_role": "public_event",
        "parent_event_id": None,
        "source": {"dataset": dataset, "source_event_id": source_id},
        "nycif": {"event_date": date},
    }


def test_distinct_events_do_not_trigger_duplicate_gate():
    report = mod.audit([
        event("a", "Marine Park Concert", source_id="1"),
        event("b", "Brooklyn Family Day", start="2026-08-08T14:00:00-04:00", source_id="2"),
    ])
    assert report["release_gate"] == "PASS"
    assert report["exact_candidate_group_count"] == 0
    assert report["near_candidate_group_count"] == 0


def test_same_occurrence_across_sources_requires_review_not_auto_merge():
    report = mod.audit([
        event("a", "JCC Summer Festival", dataset="city", source_id="100"),
        event("b", "JCC Summer Festival", dataset="community", source_id="abc"),
    ])
    assert report["release_gate"] == "REVIEW_REQUIRED"
    assert report["exact_candidate_group_count"] == 1
    assert report["exact_groups"][0]["auto_merge_allowed"] is False


def test_title_normalization_catches_punctuation_variation():
    report = mod.audit([
        event("a", "Great 6th Avenue Festival", dataset="city", source_id="1"),
        event("b", "Great 6th-Avenue Festival!", dataset="permit", source_id="2"),
    ])
    assert report["release_gate"] == "REVIEW_REQUIRED"
    assert report["exact_candidate_group_count"] == 1


def test_same_title_different_time_same_borough_is_near_candidate():
    report = mod.audit([
        event("a", "Community Softball Final", dataset="league", source_id="1"),
        event("b", "Community Softball Final", start="2026-08-08T16:00:00-04:00", location="McGuire Fields", dataset="community", source_id="2"),
    ])
    assert report["release_gate"] == "REVIEW_REQUIRED"
    assert report["near_candidate_group_count"] == 1


def test_audit_never_merges_or_rewrites_input():
    rows = [event("a", "Festival", dataset="a"), event("b", "Festival", dataset="b", source_id="2")]
    original = [dict(row) for row in rows]
    mod.audit(rows)
    assert rows == original
