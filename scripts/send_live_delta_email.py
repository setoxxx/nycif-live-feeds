#!/usr/bin/env python3
"""Email NYCIF live delta report when newly added events are found.

This script is safe to run in GitHub Actions. If SMTP secrets are missing or if there
are no newly added events, it exits without sending.

Required env vars to send:
- SMTP_HOST
- SMTP_PORT
- SMTP_USERNAME
- SMTP_PASSWORD
- REPORT_TO_EMAIL
- REPORT_FROM_EMAIL

Optional:
- REPORT_MAX_EVENTS, default 25
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "live_delta_report.json"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def compact_line(event: dict[str, Any]) -> str:
    title = event.get("title") or "Untitled event"
    date = event.get("date") or "Date TBA"
    time = event.get("display_time") or event.get("start_date_time") or "Time TBA"
    borough = event.get("borough") or "Borough TBA"
    location = event.get("display_location") or "Location TBA"
    event_type = event.get("event_type") or event.get("category") or "event"
    source_id = event.get("source_event_id") or ""
    suffix = f" | ID {source_id}" if source_id else ""
    return f"- {date} {time} | {borough} | {title} | {location} | {event_type}{suffix}"


def build_body(report: dict[str, Any], max_events: int) -> str:
    added = report.get("added_events") or []
    candidates = report.get("pr_outreach_candidates") or []
    summary = report.get("summary") or {}
    lines = [
        "NYCIF Live Event Update",
        "",
        f"Generated: {report.get('generated_at_utc') or 'unknown'}",
        f"Feed generated: {report.get('current_feed_generated_at_utc') or 'unknown'}",
        "",
        "Summary:",
        f"- Added: {summary.get('added', report.get('added_count', 0))}",
        f"- Removed/expired: {summary.get('removed', report.get('removed_count', 0))}",
        f"- Changed: {summary.get('changed', report.get('changed_count', 0))}",
        f"- Net change: {summary.get('net_change', report.get('net_change', 0))}",
        f"- PR outreach candidates: {summary.get('pr_outreach_candidates', report.get('pr_outreach_candidate_count', 0))}",
        "",
    ]

    if candidates:
        lines.append("Best PR outreach candidates:")
        for event in candidates[:max_events]:
            lines.append(compact_line(event))
            reasons = event.get("outreach_reasons") or []
            if reasons:
                lines.append(f"  Reason: {', '.join(str(reason) for reason in reasons)}")
        lines.append("")

    if added:
        lines.append("All newly added events:")
        for event in added[:max_events]:
            lines.append(compact_line(event))
        if len(added) > max_events:
            lines.append(f"- Plus {len(added) - max_events} more newly added events in data/live_delta_report.json")
        lines.append("")

    lines.extend([
        "Backend file:",
        "data/live_delta_report.json",
        "",
        "Note: PR candidates are leads, not confirmed contacts. Research organizer, venue, agency, or event website before outreach.",
    ])
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    smtp_host = env("SMTP_HOST")
    smtp_port = int(env("SMTP_PORT") or "587")
    smtp_username = env("SMTP_USERNAME")
    smtp_password = env("SMTP_PASSWORD")
    report_to = env("REPORT_TO_EMAIL")
    report_from = env("REPORT_FROM_EMAIL") or smtp_username

    missing = [name for name, value in {
        "SMTP_HOST": smtp_host,
        "SMTP_USERNAME": smtp_username,
        "SMTP_PASSWORD": smtp_password,
        "REPORT_TO_EMAIL": report_to,
        "REPORT_FROM_EMAIL": report_from,
    }.items() if not value]
    if missing:
        print(f"Email not sent; missing env vars: {', '.join(missing)}")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = report_from
    message["To"] = report_to
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls(context=context)
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def main() -> int:
    report = load_json_file(REPORT_PATH, {})
    if not isinstance(report, dict):
        print("Email not sent; report missing or invalid.")
        return 0

    added_count = int(report.get("added_count") or 0)
    candidate_count = int(report.get("pr_outreach_candidate_count") or 0)
    if added_count <= 0:
        print("Email not sent; no newly added events.")
        return 0

    try:
        max_events = max(1, int(env("REPORT_MAX_EVENTS") or "25"))
    except Exception:
        max_events = 25

    subject = f"NYCIF live update: {added_count} new events, {candidate_count} PR leads"
    body = build_body(report, max_events)
    send_email(subject, body)
    print(subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
