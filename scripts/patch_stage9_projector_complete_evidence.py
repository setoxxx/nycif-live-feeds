#!/usr/bin/env python3
"""Remove exception-ledger caps and emit the authoritative accepted population."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTOR = ROOT / "scripts" / "project_events_discovery_v02.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = PROJECTOR.read_text(encoding="utf-8")
    if "data/events_discovery_accepted_canonical_v02.json" in text and '"truncated": False' in text:
        print("Stage 9 projector evidence patch already installed")
        return 0

    text = replace_once(text, '"ids": [m["id"] for m in members[:20]],', '"ids": sorted(m["id"] for m in members),', "duplicate member cap")
    text = replace_once(text, '"titles": list({m["title"] for m in members})[:10],', '"titles": sorted({m["title"] for m in members}),', "duplicate title cap")
    text = replace_once(
        text,
        """    return out[:500]""",
        """    out.sort(key=lambda item: (-int(item["count"]), str(item["group_key"])))
    return out""",
        "duplicate group cap",
    )
    text = replace_once(
        text,
        '"items": legacy_report["quarantined"][:500],',
        '"items": legacy_report["quarantined"],',
        "legacy quarantine cap",
    )
    text = replace_once(text, '"items": low_conf[:2000]', '"items": low_conf', "low confidence cap")
    text = replace_once(text, '"items": missing_coords[:2000]', '"items": missing_coords', "missing coordinate cap")
    text = replace_once(text, '"items": invalid[:2000]', '"items": invalid', "invalid queue cap")
    text = replace_once(
        text,
        """    accepted, group_report = group_events(accepted)
    legacy_report = legacy_major_quarantine(accepted, legacy_major)""",
        """    accepted, group_report = group_events(accepted)
    write_json(
        "data/events_discovery_accepted_canonical_v02.json",
        envelope(accepted, generated_at_utc=generated_at, next_cursor=None)
        | {"classification_version": CLASSIFICATION_VERSION, "artifact_type": "accepted_canonical_discovery_v02"},
    )
    legacy_report = legacy_major_quarantine(accepted, legacy_major)""",
        "accepted population output",
    )
    text = replace_once(
        text,
        """    write_json(
        "data/events_discovery_possible_duplicates_v02.json",
        {"generated_at_utc": generated_at, "count": len(dupes), "groups": dupes},
    )""",
        """    duplicate_ids = {
        canonical_id
        for group in dupes
        for canonical_id in group.get("ids", [])
        if canonical_id
    }
    write_json(
        "data/events_discovery_possible_duplicates_v02.json",
        {
            "artifact_type": "events_discovery_possible_duplicates_v02",
            "schema_version": "2.0.0",
            "generated_at_utc": generated_at,
            "canonical_population_count": len(accepted),
            "count": len(dupes),
            "candidate_record_count": sum(int(group.get("count") or 0) for group in dupes),
            "unique_candidate_id_count": len(duplicate_ids),
            "truncated": False,
            "auto_merge_allowed": False,
            "groups": dupes,
        },
    )""",
        "complete duplicate artifact",
    )
    PROJECTOR.write_text(text, encoding="utf-8")
    print("Stage 9 complete-evidence projector patch installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
