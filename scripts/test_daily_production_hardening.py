#!/usr/bin/env python3
"""Deterministic regressions for the daily production hardening path."""

from __future__ import annotations

import copy
import json
import py_compile
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import sync_nyc_parks_bigapps_events as parks_sync  # noqa: E402
from scripts.build_staged_production_feed import apply_one_day_street_dedupe  # noqa: E402
from scripts.record_blocked_daily_data_health import build_payload  # noqa: E402
from scripts.refresh_official_supplemental_occurrences import occurrence_key  # noqa: E402
from scripts.run_daily_refresh_stage import failure_payload, run_command, sanitize_summary  # noqa: E402
from scripts.sync_nyc_citywide_events_calendar import bool_flag  # noqa: E402


def street_row(day: str, source_event_id: str, *, priority: int = 0) -> dict:
    return {
        "id": f"tvpp-9vvx:{source_event_id}@{day}",
        "title": "Neighborhood Open Street",
        "event_name": "Neighborhood Open Street",
        "event_type": "Street Event",
        "borough": "Brooklyn",
        "display_location": "MAIN STREET between FIRST AVENUE and SECOND AVENUE",
        "lat": 40.65,
        "lng": -73.95,
        "date": day,
        "start_date_time": f"{day}T10:00:00.000",
        "end_date_time": f"{day}T18:00:00.000",
        "source_dataset": "tvpp-9vvx",
        "source_event_id": source_event_id,
        "source_cemsid": ["CEMS-123"],
        "priority_score": priority,
        "needs_review": False,
    }


def test_recurring_dates_are_preserved() -> None:
    first = street_row("2026-08-01", "1001")
    second = street_row("2026-08-08", "1002")
    kept, rejected = apply_one_day_street_dedupe([first, second])
    assert len(kept) == 2, kept
    assert rejected == [], rejected


def test_exact_occurrence_duplicate_is_suppressed() -> None:
    first = street_row("2026-08-01", "1001", priority=1)
    duplicate = copy.deepcopy(first)
    duplicate["source_event_id"] = "1001-copy"
    duplicate["id"] = "tvpp-9vvx:1001-copy@2026-08-01"
    duplicate["priority_score"] = 9
    kept, rejected = apply_one_day_street_dedupe([first, duplicate])
    assert len(kept) == 1, kept
    assert len(rejected) == 1, rejected
    assert kept[0]["source_event_id"] == "1001-copy", kept


def calendar_base() -> dict:
    return {
        "source_dataset": "nyc-citywide-events-calendar-api",
        "source_event_id": "abc",
        "title": "Recurring workshop",
    }


def test_calendar_occurrence_identity_includes_date() -> None:
    first = {**calendar_base(), "start_date_time": "2026-08-01T10:00:00"}
    second = {**calendar_base(), "start_date_time": "2026-08-08T10:00:00"}
    assert occurrence_key(first) != occurrence_key(second)


def test_calendar_occurrence_identity_includes_same_day_time() -> None:
    morning = {**calendar_base(), "start_date_time": "2026-08-01T10:00:00"}
    afternoon = {**calendar_base(), "start_date_time": "2026-08-01T14:00:00"}
    assert occurrence_key(morning) != occurrence_key(afternoon)


def test_calendar_cancellation_flags_are_typed_safely() -> None:
    assert bool_flag(True) is True
    assert bool_flag("true") is True
    assert bool_flag("1") is True
    assert bool_flag(False) is False
    assert bool_flag("false") is False
    assert bool_flag("0") is False
    assert bool_flag(None) is False


def test_parks_source_contract_uses_official_open_data_tables() -> None:
    assert parks_sync.EVENTS_DATASET_ID == "fudw-fgrp"
    assert parks_sync.LOCATIONS_DATASET_ID == "cpcm-i88g"
    assert parks_sync.CATEGORIES_DATASET_ID == "xtsw-fqvh"
    assert parks_sync.SOURCE_CONTRACT_VERSION == "NYCIF_PARKS_EVENTS_OPEN_DATA_V2"


def test_parks_exact_event_id_join_and_single_point_behavior() -> None:
    locations = parks_sync.related_index(
        [
            {"event_id": "42", "name": "Demo Park", "lat": "40.7001", "long": "-73.9001"},
            {"event_id": "99", "name": "Other Park", "lat": "40.7101", "long": "-73.9101"},
        ]
    )
    assert [row["name"] for row in locations["42"]] == ["Demo Park"]
    result = parks_sync.normalize_event_item(
        {"event_id": "42", "title": "Park event", "date": "2026-08-10", "start_time": "10:00 AM"},
        locations["42"],
        [],
    )
    assert result["lat"] == 40.7001
    assert result["lng"] == -73.9001
    assert result["source_coordinate_state"] == "single_source_location_point"
    assert result["source_dataset"] == "nyc-parks-bigapps-events"
    assert result["source_authority_dataset"] == "fudw-fgrp"
    assert result["promotion_allowed"] is False
    assert result["public_map_modified"] is False


def test_parks_multiple_source_points_abstain_from_guessing() -> None:
    result = parks_sync.normalize_event_item(
        {"event_id": "42", "title": "Multi-location event", "date": "2026-08-10"},
        [
            {"event_id": "42", "name": "A", "lat": "40.7001", "long": "-73.9001"},
            {"event_id": "42", "name": "B", "lat": "40.7101", "long": "-73.9101"},
        ],
        [],
    )
    assert result["lat"] is None
    assert result["lng"] is None
    assert result["source_coordinate_count"] == 2
    assert result["source_coordinate_state"] == "multiple_source_location_points"


def test_parks_live_failure_stays_non_live() -> None:
    committed = [
        {
            "source_event_id": "saved",
            "start_date": "2099-01-01",
            "end_date": "2099-01-01",
        }
    ]
    with patch.object(parks_sync, "fetch_official_tables", side_effect=RuntimeError("boom")), patch.object(
        parks_sync, "load_committed_snapshot_events", return_value=committed
    ), patch.object(parks_sync, "save_json"), patch("builtins.print") as mocked_print:
        code = parks_sync.main()
    assert code == 0
    report_text = mocked_print.call_args.args[0]
    assert '"fetch_mode": "committed_snapshot_fallback"' in report_text
    assert '"fetch_mode": "live"' not in report_text


def test_failure_summary_redacts_common_secrets() -> None:
    summary = sanitize_summary(
        "request failed?access_token=abc123 token=secret-value Authorization=Bearer-secret"
    )
    assert "abc123" not in summary
    assert "secret-value" not in summary
    assert "Bearer-secret" not in summary
    assert summary.count("[REDACTED]") >= 3


def test_failure_payload_never_emits_unknown_stage() -> None:
    payload = failure_payload(
        stage="unknown_stage",
        command_id="regression_fixture",
        exit_code=9,
        exception_class="ProcessExitError",
        error_summary="fixture failure",
    )
    assert payload["stage"] == "platform_or_uninstrumented_failure"
    assert payload["public_feed_commit_occurred"] is False


def test_stage_runner_records_actionable_failure() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        failure_file = Path(directory) / "failure.json"
        exit_code = run_command(
            [sys.executable, "-c", "import sys; print('token=top-secret'); sys.exit(7)"],
            stage="preflight_regression_fixture",
            command_id="intentional_failure_fixture",
            failure_file=failure_file,
        )
        payload = json.loads(failure_file.read_text(encoding="utf-8"))
        assert exit_code == 7
        assert payload["stage"] == "preflight_regression_fixture"
        assert payload["command_id"] == "intentional_failure_fixture"
        assert payload["exit_code"] == 7
        assert payload["exception_class"] == "ProcessExitError"
        assert payload["public_feed_commit_occurred"] is False
        assert "top-secret" not in payload["error_summary"]
        assert "[REDACTED]" in payload["error_summary"]


def test_blocked_health_payload_is_fail_closed_and_actionable() -> None:
    payload = build_payload(
        stage="unknown_stage",
        command_id="preflight_fixture",
        exit_code=3,
        shell_line="44",
        exception_class="AssertionError",
        error_summary="api_key=hunter2",
        previous_commit="abc123",
        public_feed_commit_occurred=False,
    )
    blocker = payload["blockers"][0]
    assert payload["status"] == "BLOCKED"
    assert payload["release_ready"] is False
    assert blocker["stage"] == "platform_or_uninstrumented_failure"
    assert blocker["command_id"] == "preflight_fixture"
    assert blocker["exception_class"] == "AssertionError"
    assert blocker["public_feed_commit_occurred"] is False
    assert "hunter2" not in blocker["error_summary"]
    assert payload["rollback"]["previous_public_feed_commit"] == "abc123"


def test_current_preflight_does_not_require_mutable_historical_pages() -> None:
    runner = (ROOT / "scripts" / "test_live_event_intake_refresh_current.py").read_text(
        encoding="utf-8"
    )
    assert "test_required_event_public_feed_gate" in runner
    assert "test_required_event_aug2_real_certificate_passes" in runner
    assert "test_required_event_aug1_real_approved_pages_pass" not in runner


def test_refresh_workflow_has_structured_preflight_diagnostics() -> None:
    workflow = (ROOT / ".github" / "workflows" / "discovery-feed-refresh.yml").read_text(
        encoding="utf-8"
    )
    transaction = (ROOT / "scripts" / "run_discovery_feed_refresh.sh").read_text(
        encoding="utf-8"
    )
    publisher = (ROOT / "scripts" / "publish_blocked_daily_refresh.sh").read_text(
        encoding="utf-8"
    )
    assert "bash scripts/run_discovery_feed_refresh.sh" in workflow
    assert "bash scripts/publish_blocked_daily_refresh.sh" in workflow
    assert "scripts/run_daily_refresh_stage.py" in transaction
    assert "scripts/test_live_event_intake_refresh_current.py" in transaction
    assert "--command-id" in transaction
    assert "platform_or_uninstrumented_failure" in publisher
    assert "--exception-class" in publisher
    assert "--error-summary" in publisher
    assert 'stage="unknown_stage"' not in workflow


def test_refresh_transaction_live_fetches_supplemental_sources_before_reconciliation() -> None:
    transaction = (ROOT / "scripts" / "run_discovery_feed_refresh.sh").read_text(
        encoding="utf-8"
    )
    calendar = "python scripts/sync_nyc_citywide_events_calendar.py"
    parks = "python scripts/sync_nyc_parks_bigapps_events.py"
    reconcile = "python scripts/refresh_official_supplemental_occurrences.py"
    assert calendar in transaction
    assert parks in transaction
    assert reconcile in transaction
    assert transaction.index(calendar) < transaction.index(reconcile)
    assert transaction.index(parks) < transaction.index(reconcile)
    assert '"official_citywide_calendar_live_fetch"' in transaction
    assert '"official_parks_live_fetch"' in transaction


def test_modified_reliability_python_files_compile() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        output = Path(directory)
        for source in (
            ROOT / "scripts" / "run_daily_refresh_stage.py",
            ROOT / "scripts" / "record_blocked_daily_data_health.py",
            ROOT / "scripts" / "sync_nyc_parks_bigapps_events.py",
            ROOT / "scripts" / "test_nyc_parks_open_data_sync.py",
            ROOT / "scripts" / "test_live_event_intake_refresh_current.py",
            ROOT / "scripts" / "test_daily_production_hardening.py",
        ):
            py_compile.compile(
                str(source),
                cfile=str(output / f"{source.stem}.pyc"),
                doraise=True,
            )


def main() -> int:
    tests = [
        test_recurring_dates_are_preserved,
        test_exact_occurrence_duplicate_is_suppressed,
        test_calendar_occurrence_identity_includes_date,
        test_calendar_occurrence_identity_includes_same_day_time,
        test_calendar_cancellation_flags_are_typed_safely,
        test_parks_source_contract_uses_official_open_data_tables,
        test_parks_exact_event_id_join_and_single_point_behavior,
        test_parks_multiple_source_points_abstain_from_guessing,
        test_parks_live_failure_stays_non_live,
        test_failure_summary_redacts_common_secrets,
        test_failure_payload_never_emits_unknown_stage,
        test_stage_runner_records_actionable_failure,
        test_blocked_health_payload_is_fail_closed_and_actionable,
        test_current_preflight_does_not_require_mutable_historical_pages,
        test_refresh_workflow_has_structured_preflight_diagnostics,
        test_refresh_transaction_live_fetches_supplemental_sources_before_reconciliation,
        test_modified_reliability_python_files_compile,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
