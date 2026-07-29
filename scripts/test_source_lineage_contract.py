#!/usr/bin/env python3
"""Focused tests for the Enigma source-lineage registry contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "source_lineage_registry_v01.json"


def load_entries() -> list[dict]:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    raw_entries = payload["entries"]
    entry_fields = payload.get("entry_fields")
    defaults = payload.get("entry_defaults") or {}
    entries = []
    for raw_entry in raw_entries:
        expanded = dict(defaults)
        if isinstance(raw_entry, dict):
            expanded.update(raw_entry)
        else:
            expanded.update(dict(zip(entry_fields, raw_entry)))
        entries.append(expanded)
    return entries


def by_id(entries: list[dict], entry_id: str) -> dict:
    for entry in entries:
        if entry["id"] == entry_id:
            return entry
    raise AssertionError(f"missing registry entry {entry_id}")


def main() -> int:
    entries = load_entries()

    generated_as_raw = [entry["id"] for entry in entries if entry["generated_output"] and entry["raw_intake_countable"]]
    assert not generated_as_raw, f"generated outputs counted as raw intake: {generated_as_raw}"

    historical_current = [entry["id"] for entry in entries if entry["historical_only"] and entry["raw_intake_countable"]]
    assert not historical_current, f"historical snapshots counted as current intake: {historical_current}"

    duplicate_errors = [
        entry["id"]
        for entry in entries
        if entry["duplicative_copy"] and entry["primary_role"] != "duplicative_copy"
    ]
    assert not duplicate_errors, f"duplicative copies lack explicit duplicate role: {duplicate_errors}"

    public_surface_missing_risk = [
        entry["id"]
        for entry in entries
        if (entry["can_affect_public_map"] or entry["can_affect_wordpress"])
        and entry["public_surface_risk"] not in {"low", "medium", "high"}
    ]
    assert not public_surface_missing_risk, f"public-surface entries missing risk classification: {public_surface_missing_risk}"

    occurrence_source_only = [
        entry["id"]
        for entry in entries
        if entry["requires_occurrence_key"] and entry["identity_granularity"] == "source_id_only"
    ]
    assert not occurrence_source_only, f"occurrence-required rows use source_id_only: {occurrence_source_only}"

    review_public_ready = [entry["id"] for entry in entries if entry["review_only"] and entry["public_ready"]]
    assert not review_public_ready, f"review-only feeds marked public-ready: {review_public_ready}"

    national = by_id(entries, "repo:national-pilot")
    assert national["primary_role"] == "national_expansion_pilot"
    assert "region" in national["national_expansion_role"], "national pilot must use a region/city/source abstraction"

    public_generated_without_performance_role = [
        entry["id"]
        for entry in entries
        if entry["generated_output"]
        and (entry["can_affect_public_map"] or entry["can_affect_event_list"])
        and entry["performance_role"] not in {
            "small_boot_feed",
            "major_default_feed",
            "paginated_approved_feed",
            "paginated_review_feed",
            "generated_static_feed",
            "admin_only_feed",
        }
    ]
    assert not public_generated_without_performance_role, (
        "public-facing generated outputs lack performance role: "
        f"{public_generated_without_performance_role}"
    )

    location_cache = by_id(entries, "lf:location-cache")
    assert location_cache["path_or_source"] == "data/location_cache.json"
    assert location_cache["primary_role"] == "reference_cache"
    assert location_cache["can_affect_location_cache"] is True
    assert location_cache["raw_intake_countable"] is False
    assert location_cache["generated_output"] is False
    assert location_cache["launch_gate_status"] == "protected_no_write"

    print("source-lineage registry contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
