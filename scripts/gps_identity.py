#!/usr/bin/env python3
"""Shared GPS identity helper for the active scripts/ pipeline.

Canonical Milestone 7-A foundation module. Each public function is a
compatibility-preserving copy of an identity algorithm that already exists in
the active pipeline, so that Canonical Milestone 7-B can migrate callers onto
one shared implementation without changing any identity output bit-for-bit.

No caller is migrated by this module's introduction. The original definitions
remain in place in their owning scripts until a separately authorized
migration.

Compatibility profiles preserved here (see
docs/canonical_milestone_7a_normalization_inventory.md for the full survey):

- ``normalize_text_legacy`` — the ``norm()`` function defined identically in
  nine active scripts (build_gps_repository.py, build_gps_review_groups.py,
  build_gps_geocoding_filled_proposals.py, build_location_cache.py,
  build_staged_production_feed.py, build_test_enriched_feed.py,
  sync_nyc_open_data.py, audit_feed_anomalies.py, audit_row_disposition.py).
  No ampersand expansion.
- ``normalize_text_with_ampersand`` — the ``norm_text()`` function in
  build_gps_manual_approval_staging.py and the ``normalize()`` function in
  generate_gps_staged_feed_integration_match_diagnostic.py and
  apply_gps_staged_feed_integration_update.py (three bit-identical copies).
  Expands ``&`` to `` and `` before stripping punctuation.

The two profiles are intentionally NOT collapsed: ``build_group_key`` (and the
location-cache candidate keys) use the legacy profile, while
``build_stable_identity_key``'s display fallback and
``build_stable_event_identity`` use the ampersand profile. Collapsing them
would change persisted identity for any value containing ``&``.

This module must remain:

- deterministic (no current time, no randomness);
- side-effect free (no mutation of caller-owned input);
- free of file, network, environment-variable, and geocoding access;
- free of global mutable state;
- independent of ``review_rank`` and row position (neither is ever read).
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "normalize_text_legacy",
    "normalize_text_with_ampersand",
    "row_location",
    "event_cemsids",
    "build_group_key",
    "build_stable_identity_key",
    "build_stable_event_identity",
    "build_repository_candidate_keys",
]


def normalize_text_legacy(value: Any) -> str:
    """Legacy normalization profile (``norm()`` in nine active scripts).

    Lowercases, replaces every run of characters outside ``[a-z0-9]`` with a
    single space, and strips. ``None``, ``0``, ``False``, and ``""`` all
    normalize to ``""`` because the originals coerce with ``str(value or "")``.
    Ampersands are punctuation under this profile: ``"A & B"`` -> ``"a b"``.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_text_with_ampersand(value: Any) -> str:
    """Ampersand-expanding normalization profile.

    Preserves ``norm_text()`` (build_gps_manual_approval_staging.py) and
    ``normalize()`` (generate_gps_staged_feed_integration_match_diagnostic.py,
    apply_gps_staged_feed_integration_update.py), which are bit-identical.
    ``"A & B"`` -> ``"a and b"``. All other behavior matches the legacy
    profile, including ``str(value or "")`` falsy coercion.
    """
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def row_location(row: dict[str, Any]) -> str:
    """Staged-feed location accessor used by ``stable_event_identity``.

    Preserves ``row_location()`` from
    generate_gps_staged_feed_integration_match_diagnostic.py and
    apply_gps_staged_feed_integration_update.py exactly: precedence
    ``display_location`` -> ``location`` -> ``event_location``, no ``address``
    fallback, and — unlike the grouping/repository accessors — NO ``.strip()``.
    """
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "")


def event_cemsids(row: dict[str, Any]) -> set[str]:
    """Staged-feed CEMSID set used by ``stable_event_identity``.

    Preserves ``event_cemsids()`` from the two staged-feed scripts exactly:
    each list item is converted with ``str()`` and included only when the
    converted string is non-empty (items are NOT stripped, so ``None`` -> the
    string ``"None"``, ``0`` -> ``"0"``, and ``False`` -> ``"False"`` are all
    included); any other truthy value becomes a one-element set; and — unlike
    the repository's ``split_ids()`` — a comma-separated string is NOT split.
    The loop form (rather than the callers' set comprehension) satisfies a
    SonarQube always-true-condition finding with identical semantics.
    """
    raw = row.get("source_cemsid") or row.get("cemsid") or []
    if isinstance(raw, list):
        values: set[str] = set()
        for item in raw:
            text = str(item)
            if text:
                values.add(text)
        return values
    if raw:
        return {str(raw)}
    return set()


def _borough_text(row: dict[str, Any]) -> str:
    """Shared borough accessor (``borough()`` in build_gps_review_groups.py and
    ``borough_text()`` in build_gps_repository.py are bit-identical)."""
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def _review_group_location(row: dict[str, Any]) -> str:
    """Grouping location accessor (``location()`` in
    build_gps_review_groups.py): no ``address`` fallback, stripped."""
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "").strip()


def _repository_location_text(row: dict[str, Any]) -> str:
    """Repository location accessor (``location_text()`` in
    build_gps_repository.py): includes the ``address`` fallback, stripped.
    Deliberately distinct from ``_review_group_location``."""
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or row.get("address") or "").strip()


def _repository_title_text(row: dict[str, Any]) -> str:
    """Repository title accessor (``title_text()`` in build_gps_repository.py):
    precedence ``title`` -> ``event_name`` -> ``name``."""
    return str(row.get("title") or row.get("event_name") or row.get("name") or "").strip()


def _source_event_id(row: dict[str, Any]) -> str:
    """Source-event-id accessor (``source_event_id()`` in
    build_gps_repository.py and build_gps_review_groups.py, bit-identical)."""
    return str(row.get("source_event_id") or row.get("event_id") or "").strip()


def _split_ids(value: Any) -> list[str]:
    """Repository CEMSID splitter (``split_ids()`` in build_gps_repository.py):
    lists are stripped per item; strings are comma-split and stripped. Order
    is preserved exactly as given."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _repository_date_key(row: dict[str, Any]) -> str:
    """Repository date key (``date_key()`` in build_gps_repository.py):
    leading ``YYYY-MM-DD`` of ``date`` -> ``start_date_time`` -> ``start``,
    else ``""``."""
    raw = str(row.get("date") or row.get("start_date_time") or row.get("start") or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def build_group_key(row: dict[str, Any]) -> str:
    """Review-group identity (``group_key()`` in build_gps_review_groups.py).

    ``f"{norm(borough)}|{norm(location)}"`` using the legacy normalization
    profile and the grouping location accessor (no ``address`` fallback).
    A row with neither component still yields ``"|"``, exactly as the
    original does.
    """
    return f"{normalize_text_legacy(_borough_text(row))}|{normalize_text_legacy(_review_group_location(row))}"


def build_stable_identity_key(row: dict[str, Any]) -> str:
    """Registry-side stable identity (``stable_key()`` in
    build_gps_manual_approval_staging.py).

    If the row carries a non-blank ``group_key`` it is stripped, lowercased
    (NOT re-normalized), and prefixed ``group:``. Otherwise the fallback is
    ``display:`` plus the ampersand-profile normalization of
    ``display_location`` — including the ``display:`` empty-suffix case when
    ``display_location`` is blank, exactly as the original behaves.
    """
    group_key = str(row.get("group_key") or "").strip().lower()
    if group_key:
        return f"group:{group_key}"
    return f"display:{normalize_text_with_ampersand(row.get('display_location'))}"


def build_stable_event_identity(row: dict[str, Any]) -> str:
    """Staged-event natural key (``stable_event_identity()`` copy-pasted
    identically in generate_gps_staged_feed_integration_match_diagnostic.py
    and apply_gps_staged_feed_integration_update.py).

    Five pipe-joined components, in order:

    1. ``source_event_id`` -> ``event_id`` -> ``id`` (unnormalized, ``str()``);
    2. ampersand-profile normalization of ``row_location(row)``;
    3. comma-joined ``sorted(event_cemsids(row))`` — the sort makes the
       component independent of input list order and collapses duplicates
       (sets deduplicate);
    4. ``str(row.get("date") or "")`` (raw, not reduced to a date key);
    5. ``str(row.get("start_date_time") or "")``.

    ``review_rank`` and row position are never read.
    """
    return "|".join(
        [
            str(row.get("source_event_id") or row.get("event_id") or row.get("id") or ""),
            normalize_text_with_ampersand(row_location(row)),
            ",".join(sorted(event_cemsids(row))),
            str(row.get("date") or ""),
            str(row.get("start_date_time") or ""),
        ]
    )


def build_repository_candidate_keys(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Location-cache candidate keys (``candidate_keys()`` in
    build_gps_repository.py).

    Emits ``(key, key_type)`` pairs in the original's exact order:

    1. ``event_id:<id>`` when a source event id resolves;
    2. one ``cemsid:<norm borough>:<cemsid>`` per ``_split_ids`` entry, in
       input order (CEMSID values themselves are NOT normalized);
    3. ``location:<norm borough>:<norm location>`` when the repository
       location accessor (WITH ``address`` fallback) is non-blank;
    4. ``text_date_location:<norm title>:<norm borough>:<norm location>:<date key>``
       only when title, location, and date key are all non-blank.

    All normalization uses the legacy profile, exactly as the original.
    The caller-side first-writer-wins duplicate handling in
    build_gps_repository.py is intentionally NOT reproduced here; this
    function only derives keys.
    """
    keys: list[tuple[str, str]] = []
    event_id = _source_event_id(row)
    borough = _borough_text(row)
    location = _repository_location_text(row)
    if event_id:
        keys.append((f"event_id:{event_id}", "event_id"))
    for cemsid in _split_ids(row.get("source_cemsid") or row.get("cemsid")):
        keys.append((f"cemsid:{normalize_text_legacy(borough)}:{cemsid}", "cemsid"))
    if location:
        keys.append((f"location:{normalize_text_legacy(borough)}:{normalize_text_legacy(location)}", "location"))
    if _repository_title_text(row) and location and _repository_date_key(row):
        keys.append(
            (
                f"text_date_location:{normalize_text_legacy(_repository_title_text(row))}:{normalize_text_legacy(borough)}:{normalize_text_legacy(location)}:{_repository_date_key(row)}",
                "text_date_location",
            )
        )
    return keys
