"""Offline, read-only assertions on committed workflow YAML text proving the
Canonical Milestone 5 fail-closed controls. No workflow is invoked, no
repository script is imported or executed, no network access occurs, and no
third-party library is required (stdlib text/regex parsing only)."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

LIVE_SYNC_WORKFLOW = WORKFLOWS_DIR / "live-sync-qa.yml"

GPS_COMMIT_WORKFLOWS = [
    WORKFLOWS_DIR / "gps-staged-feed-integration-adjudication-summary.yml",
    WORKFLOWS_DIR / "gps-staged-feed-integration-diagnostic.yml",
    WORKFLOWS_DIR / "gps-staged-feed-integration-update.yml",
]

EXPECTED_EMAIL_CONDITION = "if: github.event.inputs.allow_email == 'yes' && env.BACKEND_GATE_FAILED != 'true'"
EXPECTED_EMAIL_RUN = "run: python scripts/send_live_delta_email.py"
EXPECTED_GATE_RUN = 'run: python scripts/backend_reliability_gate.py || echo "BACKEND_GATE_FAILED=true" >> "$GITHUB_ENV"'
EXPECTED_ENFORCE_CONDITION = "if: env.BACKEND_GATE_FAILED == 'true'"


def _text(path):
    return path.read_text(encoding="utf-8")


def _step_block(text, step_name):
    """Return the text of a single '- name: <step_name>' step block, up to
    (but excluding) the next '- name:' line at the same indentation."""
    lines = text.splitlines()
    marker = f"- name: {step_name}"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == marker:
            start = i
            break
    assert start is not None, f"step {step_name!r} not found"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("- name:"):
            end = i
            break
    return "\n".join(lines[start:end])


def _step_order(text, *step_names):
    lines = text.splitlines()
    indices = {}
    for name in step_names:
        marker = f"- name: {name}"
        for i, line in enumerate(lines):
            if line.strip() == marker:
                indices[name] = i
                break
        assert name in indices, f"step {name!r} not found"
    return [indices[name] for name in step_names]


def test_email_step_condition_is_exact_fail_closed_expression():
    block = _step_block(_text(LIVE_SYNC_WORKFLOW), "Email live delta report")
    if_lines = [l.strip() for l in block.splitlines() if l.strip().startswith("if:")]
    assert len(if_lines) == 1
    assert if_lines[0] == EXPECTED_EMAIL_CONDITION


def test_email_step_run_command_unchanged():
    block = _step_block(_text(LIVE_SYNC_WORKFLOW), "Email live delta report")
    run_lines = [l.strip() for l in block.splitlines() if l.strip().startswith("run:")]
    assert run_lines == [EXPECTED_EMAIL_RUN]


def test_email_step_env_keys_unchanged():
    block = _step_block(_text(LIVE_SYNC_WORKFLOW), "Email live delta report")
    env_keys = re.findall(r"^\s{10}([A-Z_]+):\s*\$\{\{\s*secrets\.[A-Z_]+\s*\}\}", block, re.MULTILINE)
    assert env_keys == [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "REPORT_TO_EMAIL",
        "REPORT_FROM_EMAIL",
        "REPORT_MAX_EVENTS",
    ]


def test_backend_gate_flag_producer_precedes_email_step():
    text = _text(LIVE_SYNC_WORKFLOW)
    gate_idx, email_idx = _step_order(text, "Build backend reliability gate report", "Email live delta report")
    assert gate_idx < email_idx
    gate_block = _step_block(text, "Build backend reliability gate report")
    run_lines = [l.strip() for l in gate_block.splitlines() if l.strip().startswith("run:")]
    assert run_lines == [EXPECTED_GATE_RUN]


def test_backend_gate_enforcement_follows_email_step():
    text = _text(LIVE_SYNC_WORKFLOW)
    email_idx, enforce_idx = _step_order(text, "Email live delta report", "Enforce backend reliability gate")
    assert email_idx < enforce_idx
    enforce_block = _step_block(text, "Enforce backend reliability gate")
    if_lines = [l.strip() for l in enforce_block.splitlines() if l.strip().startswith("if:")]
    assert if_lines == [EXPECTED_ENFORCE_CONDITION]
    assert "exit 1" in enforce_block


def test_email_step_skipped_when_gate_failed_flag_true():
    block = _step_block(_text(LIVE_SYNC_WORKFLOW), "Email live delta report")
    assert "env.BACKEND_GATE_FAILED != 'true'" in block
    assert "env.BACKEND_GATE_FAILED == 'true'" not in block


def test_all_three_gps_commit_steps_use_if_success():
    for path in GPS_COMMIT_WORKFLOWS:
        text = _text(path)
        commit_step_names = re.findall(r"- name: (Commit .+)", text)
        assert len(commit_step_names) == 1, f"{path.name}: expected exactly one commit step"
        block = _step_block(text, commit_step_names[0])
        if_lines = [l.strip() for l in block.splitlines() if l.strip().startswith("if:")]
        assert if_lines == ["if: success()"], f"{path.name}: unexpected commit-step condition {if_lines!r}"


def test_no_gps_commit_step_uses_if_always():
    for path in GPS_COMMIT_WORKFLOWS:
        assert "if: always()" not in _text(path)


def test_live_sync_has_no_schedule_trigger():
    text = _text(LIVE_SYNC_WORKFLOW)
    trigger_block = text.split("permissions:")[0]
    assert "schedule" not in trigger_block
    assert "cron" not in trigger_block


def test_live_sync_preserves_manual_opt_in_defaults_and_job_gate():
    text = _text(LIVE_SYNC_WORKFLOW)
    assert "workflow_dispatch:" in text
    assert re.search(r"allow_live_fetch:\s*\n\s*description:.*\n\s*required:\s*true\s*\n\s*default:\s*\"no\"", text)
    assert re.search(r"allow_email:\s*\n\s*description:.*\n\s*required:\s*true\s*\n\s*default:\s*\"no\"", text)
    assert "if: github.event.inputs.allow_live_fetch == 'yes'" in text


def test_live_sync_permission_remains_contents_read():
    text = _text(LIVE_SYNC_WORKFLOW)
    permissions_block = text.split("concurrency:")[0]
    assert "permissions:" in permissions_block
    assert re.search(r"permissions:\s*\n\s*contents:\s*read", permissions_block)


def test_gps_commit_workflows_no_schedule_trigger_introduced():
    for path in GPS_COMMIT_WORKFLOWS:
        text = _text(path)
        trigger_block = text.split("permissions:")[0]
        assert "schedule" not in trigger_block
