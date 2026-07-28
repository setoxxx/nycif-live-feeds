#!/usr/bin/env python3
"""Apply the dated-occurrence identity enforcement patch to the real projector.

This is a one-time branch maintenance helper for PR #328. It patches only
scripts/project_events_discovery_v02.py and is idempotent.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTOR = ROOT / "scripts" / "project_events_discovery_v02.py"


def replace_once(text: str, old: str, new: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("expected projector snippet not found")
    return text.replace(old, new, 1)


def main() -> int:
    text = PROJECTOR.read_text(encoding="utf-8")
    original = text

    text = replace_once(
        text,
        'from schema_v1_common import DEFAULT_TIMEZONE, envelope  # noqa: E402\n',
        'from schema_v1_common import DEFAULT_TIMEZONE, envelope  # noqa: E402\n'
        'from occurrence_identity_contract import (  # noqa: E402\n'
        '    occurrence_key,\n'
        '    occurrence_key_set,\n'
        ')\n',
    )

    text = replace_once(
        text,
        '''def rejected_open_data_keys(dispositions: list[dict]) -> set[tuple[str, str]]:\n    rejected: set[tuple[str, str]] = set()\n    for row in dispositions:\n        if str(row.get("disposition") or "").lower() not in {"rejected", "drop", "invalid"} and "reject" not in str(\n            row.get("reason") or ""\n        ).lower():\n            continue\n        dataset = str(row.get("source_dataset") or "nyc-open-data").strip()\n        source_event_id = str(row.get("source_event_id") or "").strip()\n        if dataset and source_event_id:\n            rejected.add((dataset, source_event_id))\n    return rejected\n''',
        '''def rejected_open_data_keys(dispositions: list[dict]) -> set[tuple[str, str]]:\n    rejected, _occurrences = rejected_open_data_identity_sets(dispositions)\n    return rejected\n\n\ndef rejected_open_data_identity_sets(\n    dispositions: list[dict],\n) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:\n    rejected_sources: set[tuple[str, str]] = set()\n    rejected_occurrences: set[tuple[str, str, str]] = set()\n    for row in dispositions:\n        if str(row.get("disposition") or "").lower() not in {"rejected", "drop", "invalid"} and "reject" not in str(\n            row.get("reason") or ""\n        ).lower():\n            continue\n        dataset = str(row.get("source_dataset") or "nyc-open-data").strip()\n        source_event_id = str(row.get("source_event_id") or "").strip()\n        if dataset and source_event_id:\n            rejected_sources.add((dataset, source_event_id))\n            day = _parse_iso_date(row.get("date") or row.get("event_date") or row.get("start_date_time"))\n            if day:\n                rejected_occurrences.add((dataset, source_event_id, day))\n    return rejected_sources, rejected_occurrences\n''',
    )

    text = replace_once(
        text,
        '''    staged_keys = staged_source_keys(staged_rows)\n    rejected_keys = rejected_open_data_keys(rejected_disp)\n    unstaged_intake_count = 0\n    for i, row in enumerate(raw_rows):\n        dataset, source_event_id = source_parts_safe(row)\n        if (dataset, source_event_id) in staged_keys:\n            continue\n        if (dataset, source_event_id) in rejected_keys:\n            continue\n        if not event_overlaps_season(row, SEASON_START_DATE, SEASON_END_DATE):\n            continue\n''',
        '''    staged_keys = staged_source_keys(staged_rows)\n    staged_occurrence_keys = occurrence_key_set(staged_rows)\n    rejected_keys, rejected_occurrence_keys = rejected_open_data_identity_sets(rejected_disp)\n    unstaged_intake_count = 0\n    for i, row in enumerate(raw_rows):\n        dataset, source_event_id = source_parts_safe(row)\n        raw_occurrence_key = occurrence_key(row)\n        if raw_occurrence_key in staged_occurrence_keys:\n            continue\n        if raw_occurrence_key in rejected_occurrence_keys or (dataset, source_event_id) in rejected_keys:\n            continue\n        if not event_overlaps_season(row, SEASON_START_DATE, SEASON_END_DATE):\n            continue\n''',
    )

    text = replace_once(
        text,
        '''        accepted_keys = {source_parts_safe(row) for row in staged_rows}\n        for e in accepted:\n            src = e.get("source") if isinstance(e.get("source"), dict) else {}\n            accepted_keys.add(\n                (str(src.get("dataset") or ""), str(src.get("source_event_id") or ""))\n            )\n        for i, row in enumerate(projected_rows):\n            dataset, source_event_id = source_parts_safe(row)\n            if (dataset, source_event_id) in accepted_keys:\n                continue\n''',
        '''        accepted_keys = {source_parts_safe(row) for row in staged_rows}\n        accepted_occurrence_keys = occurrence_key_set(staged_rows)\n        for e in accepted:\n            src = e.get("source") if isinstance(e.get("source"), dict) else {}\n            accepted_keys.add(\n                (str(src.get("dataset") or ""), str(src.get("source_event_id") or ""))\n            )\n            accepted_occurrence_keys.add(occurrence_key(e))\n        for i, row in enumerate(projected_rows):\n            dataset, source_event_id = source_parts_safe(row)\n            projected_occurrence_key = occurrence_key(row)\n            if projected_occurrence_key in accepted_occurrence_keys:\n                continue\n''',
    )

    text = replace_once(
        text,
        '''            accepted.append(event)\n            accepted_keys.add((dataset, source_event_id))\n            projected_feast_count += 1\n''',
        '''            accepted.append(event)\n            accepted_keys.add((dataset, source_event_id))\n            accepted_occurrence_keys.add(projected_occurrence_key)\n            projected_feast_count += 1\n''',
    )

    text = replace_once(
        text,
        '''            "Open-data accounting uses staged + unstaged season intake + disposition rejects.",\n''',
        '''            "Open-data accounting uses staged dated occurrences + occurrence-keyed unstaged season intake + disposition rejects.",\n''',
    )

    if text == original:
        print("projector already patched")
        return 0
    PROJECTOR.write_text(text, encoding="utf-8")
    print("patched scripts/project_events_discovery_v02.py for dated occurrence identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
