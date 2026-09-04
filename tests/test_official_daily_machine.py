from scripts import official_daily_machine as machine
from scripts import official_event_contract as contract


PARKS = contract.DATASET_PARKS
TVPP = contract.DATASET_TVPP

PIN_EVIDENCE = {
    "exact_pin_eligible": True,
    "reason_code": "OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED",
}


def _row(occurrence_id: str, *, map_ready: bool = False, title: str = "Event") -> dict:
    return {
        "occurrence_id": occurrence_id,
        "title": title,
        "map_ready": map_ready,
        "display_location": "A park",
    }


def test_machine_diffs_added_and_removed_and_passes_pin_coverage(monkeypatch):
    snapshot = {
        PARKS: [
            {
                "lat": 40.7,
                "lng": -74.0,
                "location_evidence": PIN_EVIDENCE,
            }
        ],
        TVPP: [{"event_id": "1"}],
    }
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: snapshot.get(dataset, []),
    )
    report, index = machine.build_machine_report(
        {
            PARKS: [_row("aaa", map_ready=True, title="Parks pin")],
            TVPP: [_row("bbb", map_ready=False, title="Street permit")],
        },
        {PARKS: [], TVPP: []},
        previous_index={
            "datasets": {
                PARKS: {"occurrence_ids": ["aaa", "old-parks"]},
                TVPP: {"occurrence_ids": ["gone-tvpp"]},
            }
        },
    )
    assert report["qa_pass"] is True
    assert report["baseline_established"] is False
    assert report["datasets"][PARKS]["added"] == 0
    assert report["datasets"][PARKS]["still_present"] == 1
    assert report["datasets"][PARKS]["removed_from_city"] == 1
    assert "old-parks" in report["datasets"][PARKS]["removed_from_city_occurrence_id_samples"]
    assert report["datasets"][TVPP]["added"] == 1
    assert report["datasets"][TVPP]["removed_from_city"] == 1
    assert report["datasets"][PARKS]["certified_pins"] == 1
    assert report["datasets"][PARKS]["pin_eligible"] == 1
    assert index["datasets"][PARKS]["occurrence_ids"] == ["aaa"]
    assert report["expire_enabled"] is False
    assert report["location_cache_modified"] is False
    assert report["public_map_modified"] is False


def test_machine_fails_when_official_parks_pin_is_missed(monkeypatch):
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: [
            {"lat": 40.7, "lng": -74.0, "location_evidence": PIN_EVIDENCE}
        ]
        if dataset == PARKS
        else [],
    )
    report, _index = machine.build_machine_report(
        {PARKS: [_row("aaa", map_ready=False)]},
        {PARKS: []},
        previous_index={"datasets": {}},
    )
    assert report["qa_pass"] is False
    assert any(item.startswith("pin_coverage_short") for item in report["failures"])
    assert report["pin_misses"][0]["missed"] == 1


def test_machine_fails_on_silent_drop(monkeypatch):
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: [{}, {}] if dataset == PARKS else [],
    )
    report, _index = machine.build_machine_report(
        {PARKS: [_row("aaa")]},
        {PARKS: []},
        previous_index={"datasets": {}},
    )
    assert report["qa_pass"] is False
    assert any(item.startswith("silent_drop") for item in report["failures"])
    assert report["unaccounted"][0]["unaccounted"] == 1


def test_machine_fails_if_tvpp_is_pinned(monkeypatch):
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: [{}] if dataset == TVPP else [],
    )
    report, _index = machine.build_machine_report(
        {TVPP: [_row("bbb", map_ready=True)]},
        {TVPP: []},
        previous_index={"datasets": {}},
    )
    assert report["qa_pass"] is False
    assert any("list_only_dataset_pinned" in item for item in report["failures"])


def test_rejected_pin_eligible_row_is_accounted_not_a_pin_miss(monkeypatch):
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: [
            {
                "source_event_id": "bad",
                "lat": 40.7,
                "lng": -74.0,
                "location_evidence": PIN_EVIDENCE,
            },
            {
                "source_event_id": "good",
                "lat": 40.71,
                "lng": -74.01,
                "location_evidence": PIN_EVIDENCE,
            },
        ]
        if dataset == PARKS
        else [],
    )
    report, _index = machine.build_machine_report(
        {PARKS: [_row("aaa", map_ready=True)]},
        {
            PARKS: [
                {
                    "source_dataset": PARKS,
                    "source_event_id": "bad",
                    "title": "Broken interval",
                    "reason": "invalid_interval",
                }
            ]
        },
        previous_index={"datasets": {}},
    )
    assert report["qa_pass"] is True
    assert report["datasets"][PARKS]["pin_eligible"] == 1
    assert report["datasets"][PARKS]["certified_pins"] == 1
    assert report["datasets"][PARKS]["rejected"] == 1


def test_first_run_is_a_baseline_not_a_false_removal(monkeypatch):
    monkeypatch.setattr(
        machine,
        "snapshot_items",
        lambda dataset: [{}] if dataset in {PARKS, TVPP} else [],
    )
    report, _index = machine.build_machine_report(
        {PARKS: [_row("aaa")], TVPP: [_row("bbb")]},
        {PARKS: [], TVPP: []},
        previous_index={"datasets": {}},
    )
    assert report["qa_pass"] is True
    assert report["baseline_established"] is True
    assert report["datasets"][PARKS]["added"] == 1
    assert report["datasets"][PARKS]["removed_from_city"] == 0
