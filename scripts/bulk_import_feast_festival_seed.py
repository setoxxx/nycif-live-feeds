#!/usr/bin/env python3
"""Safely merge bulk feast/fair seed patches without overwriting existing rows.

Rules:
- Never delete or mutate existing seed entries by key.
- Only append new keys from the bulk patch file.
- Optional fill-missing: add display_location to existing rows only when absent.
- Writes merge QA report; does not touch protected feeds or discovery outputs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import utc_now  # noqa: E402

SEED_PATH = ROOT / "data" / "staging" / "nyc_feast_festival_reference_seed.json"
DEFAULT_PATCH = ROOT / "data" / "staging" / "nyc_feast_festival_reference_seed_bulk_patch.json"
REPORT_PATH = ROOT / "data" / "reports" / "nyc_feast_festival_seed_bulk_merge_report.json"

EMOJI_BY_KIND = {
    "religious_feast": "🎡",
    "street_fair": "🎉",
    "food_festival": "🍽️",
    "cultural_festival": "🎊",
    "holiday_market": "🎄",
    "parade": "🎊",
}

REQUIRED = ("key", "canonical_name", "projected_start", "projected_end", "borough", "display_location")


def slug_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def validate_entry(entry: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED:
        if not str(entry.get(field) or "").strip():
            errors.append(f"row {index}: missing {field}")
    start = str(entry.get("projected_start") or "")
    end = str(entry.get("projected_end") or "")
    if start and end and end < start:
        errors.append(f"row {index}: end before start for {entry.get('key')}")
    kind = str(entry.get("event_kind") or "street_fair")
    if kind not in EMOJI_BY_KIND:
        errors.append(f"row {index}: unknown event_kind {kind}")
    return errors


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    kind = str(entry.get("event_kind") or "street_fair")
    start = str(entry.get("projected_start") or "").strip()
    end = str(entry.get("projected_end") or start).strip()
    key = str(entry.get("key") or slug_key(entry.get("canonical_name") or "")).strip()
    aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
    name = str(entry.get("canonical_name") or "").strip()
    if name and name not in aliases:
        aliases = [name, *aliases]
    return {
        "key": key,
        "canonical_name": name,
        "aliases": aliases[:8],
        "claimed_permit_id": entry.get("claimed_permit_id"),
        "projected_start": start,
        "projected_end": end,
        "event_kind": kind,
        "map_emoji": entry.get("map_emoji") or EMOJI_BY_KIND.get(kind, "🎉"),
        "typical_multi_day": bool(entry.get("typical_multi_day", end > start)),
        "borough": str(entry.get("borough") or "").strip(),
        "location_hint": str(entry.get("location_hint") or "").strip() or None,
        "display_location": str(entry.get("display_location") or "").strip(),
        "reference_lat": entry.get("reference_lat"),
        "reference_lng": entry.get("reference_lng"),
        "source": str(entry.get("source") or "google_studio_bulk_patch"),
        "bulk_import_batch": entry.get("bulk_import_batch") or "operator_google_studio_2026",
    }


def merge_seed(
    seed: dict[str, Any],
    patch_entries: list[dict[str, Any]],
    *,
    fill_missing_display: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    existing = [e for e in (seed.get("entries") or []) if isinstance(e, dict)]
    by_key = {str(e.get("key") or ""): e for e in existing if e.get("key")}

    added: list[str] = []
    skipped_duplicate: list[str] = []
    filled_display: list[str] = []
    validation_errors: list[str] = []

    for idx, raw in enumerate(patch_entries):
        if not isinstance(raw, dict):
            validation_errors.append(f"row {idx}: not an object")
            continue
        errors = validate_entry(raw, index=idx)
        if errors:
            validation_errors.extend(errors)
            continue
        entry = normalize_entry(raw)
        key = entry["key"]
        if key in by_key:
            if fill_missing_display and not by_key[key].get("display_location") and entry.get("display_location"):
                by_key[key]["display_location"] = entry["display_location"]
                filled_display.append(key)
            else:
                skipped_duplicate.append(key)
            continue
        by_key[key] = entry
        added.append(key)

    merged_entries = list(by_key.values())
    merged_entries.sort(key=lambda e: (str(e.get("projected_start") or ""), str(e.get("canonical_name") or "")))

    out_seed = {
        **seed,
        "artifact_type": "nyc_feast_festival_reference_seed",
        "version": int(seed.get("version") or 1) + (1 if added else 0),
        "last_bulk_merge_at_utc": utc_now() if added else seed.get("last_bulk_merge_at_utc"),
        "notes": list(
            dict.fromkeys(
                [
                    *(seed.get("notes") or []),
                    "Bulk patches merge append-only by key; existing rows are never overwritten.",
                    "claimed_permit_id values are hints only and frequently mismatch the committed raw snapshot.",
                ]
            )
        ),
        "entries": merged_entries,
    }

    report = {
        "artifact_type": "nyc_feast_festival_seed_bulk_merge_report",
        "generated_at_utc": utc_now(),
        "qa_pass": len(validation_errors) == 0,
        "seed_before": len(existing),
        "patch_rows": len(patch_entries),
        "added_count": len(added),
        "skipped_duplicate_count": len(skipped_duplicate),
        "filled_display_location_count": len(filled_display),
        "seed_after": len(merged_entries),
        "validation_errors": validation_errors[:50],
        "added_keys_sample": added[:40],
        "skipped_duplicate_sample": skipped_duplicate[:40],
    }
    return out_seed, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely merge bulk feast seed patch (append-only).")
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH, help="Bulk patch JSON path")
    parser.add_argument("--seed", type=Path, default=SEED_PATH, help="Seed file to update")
    parser.add_argument(
        "--fill-missing-display",
        action="store_true",
        help="Fill display_location on existing keys only when currently missing.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write seed file")
    args = parser.parse_args()

    if not args.seed.exists():
        raise SystemExit(f"Missing seed: {args.seed}")
    if not args.patch.exists():
        raise SystemExit(f"Missing patch: {args.patch}")

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    patch_payload = json.loads(args.patch.read_text(encoding="utf-8"))
    patch_entries = patch_payload.get("entries") if isinstance(patch_payload, dict) else patch_payload
    if not isinstance(patch_entries, list):
        raise SystemExit("Patch file must contain an entries array.")

    merged, report = merge_seed(seed, patch_entries, fill_missing_display=args.fill_missing_display)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.dry_run and (report["added_count"] > 0 or report["filled_display_location_count"] > 0):
        args.seed.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
