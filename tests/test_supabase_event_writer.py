import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).parents[1] / "scripts" / "supabase_event_writer.py"
SPEC = importlib.util.spec_from_file_location("supabase_event_writer", PATH)
writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(writer)


APPROVED = {
    "SUPABASE_WRITE_ENABLED": "true",
    "SUPABASE_TARGET_ENV": "staging",
    "SUPABASE_PROJECT_REF": "oggwpvdirkrnzoolparx",
    "SUPABASE_URL": "https://oggwpvdirkrnzoolparx.supabase.co",
}


@pytest.mark.parametrize(
    "overrides",
    [
        {"SUPABASE_WRITE_ENABLED": "false"},
        {"SUPABASE_TARGET_ENV": "production"},
        {"SUPABASE_PROJECT_REF": "aaaaaaaaaaaaaaaaaaaa"},
        {"SUPABASE_URL": "https://aaaaaaaaaaaaaaaaaaaa.supabase.co"},
        {"SUPABASE_URL": "http://oggwpvdirkrnzoolparx.supabase.co"},
        {"SUPABASE_PRODUCTION_REFS": "oggwpvdirkrnzoolparx"},
        {"SUPABASE_PRODUCTION_URLS": "https://oggwpvdirkrnzoolparx.supabase.co"},
    ],
)
def test_write_guard_fails_closed(overrides):
    env = {**APPROVED, **overrides}
    with pytest.raises(writer.WriteGuardError):
        writer.validate_write_target(env)


def test_write_guard_accepts_only_exact_staging_pair():
    assert writer.validate_write_target(APPROVED) == (
        "oggwpvdirkrnzoolparx",
        "https://oggwpvdirkrnzoolparx.supabase.co",
    )


def test_dry_run_contract_is_unchanged(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "input.json"
    snapshot_path = tmp_path / "snapshot.json"
    report_path = tmp_path / "report.json"
    input_path.write_text(json.dumps({"events": [{"id": "one"}]}))
    snapshot_path.write_text(json.dumps({"occurrences": {"one": {}}}))
    monkeypatch.setattr(writer, "REPORT_PATH", report_path)
    monkeypatch.setattr(
        "sys.argv",
        ["writer", "--input", str(input_path), "--supabase-snapshot", str(snapshot_path)],
    )
    writer.main()
    report = json.loads(report_path.read_text())
    assert report["run_type"] == "dry_run"
    assert report["actions"]["UNCHANGED"] == 0  # legacy comparator semantics retained
    assert report["actions"]["UPDATE"] == 1
    assert report["database_write_performed"] is False
    assert "dry_run" in capsys.readouterr().out


def test_normalizer_preserves_occurrence_identity():
    identity = "a" * 64
    event = {
        "id": "human-readable-canonical-id",
        "occurrence_id": identity,
        "title": "Synthetic Rung 8",
        "start_date_time": "2026-08-19T10:00:00-04:00",
        "source": {"dataset": "rung8-fixture", "source_event_id": "insert-1"},
        "nycif": {"classification_reason": "synthetic_fixture"},
    }
    assert writer.normalize_event(event)["occurrence_id"] == identity


def test_normalizer_uses_existing_occurrence_identity_v2_authority():
    event = {
        "id": "tvpp-9vvx:899248@2026-09-05",
        "title": "Canonical event",
        "start_date_time": "2026-09-05T14:00:00.000",
        "timezone": "America/New_York",
        "source": {"dataset": "tvpp-9vvx", "source_event_id": "899248"},
    }
    assert writer.normalize_event(event)["occurrence_id"] == (
        "0047c70a53585d3fa94e6e0bbfcd8e664a1aaab931d6535491abbec9b8161221"
    )


def test_normalizer_rejects_non_v2_identity():
    with pytest.raises(ValueError):
        writer.normalize_event(
            {"id": "not-v2", "title": "bad", "source": {"dataset": "x", "source_event_id": "y"}}
        )
