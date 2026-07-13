"""Canonical Milestone 7-A: shared GPS identity helper compatibility tests.

Proves that every function in scripts/gps_identity.py reproduces the existing
active-pipeline identity algorithms bit-for-bit, without migrating any caller
and without touching the historical (xri_g6-g11) or fixture-only (xri_g40-g44)
identity systems.

The oracles below are copied verbatim from the current caller sources (file
and line references in each docstring) so the helper is tested against the
algorithms as they exist in the callers today, not against itself. Golden
literal expectations anchor key cases independently of both implementations.
"""

from __future__ import annotations

import builtins
import copy
import importlib
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.gps_identity import (
    build_group_key,
    build_repository_candidate_keys,
    build_stable_event_identity,
    build_stable_identity_key,
    event_cemsids,
    normalize_text_legacy,
    normalize_text_with_ampersand,
    row_location,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Oracles: verbatim copies of the algorithms as they exist in active callers.
# ---------------------------------------------------------------------------


def oracle_norm(value: Any) -> str:
    """Verbatim ``norm()`` from scripts/build_gps_repository.py:60 (defined
    identically in eight further scripts; see the M7-A inventory doc)."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def oracle_norm_text(value: Any) -> str:
    """Verbatim ``norm_text()`` from scripts/build_gps_manual_approval_staging.py:66
    (bit-identical to ``normalize()`` in the two staged-feed scripts)."""
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def oracle_review_group_borough(row: dict[str, Any]) -> str:
    """Verbatim ``borough()`` from scripts/build_gps_review_groups.py:74."""
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def oracle_review_group_location(row: dict[str, Any]) -> str:
    """Verbatim ``location()`` from scripts/build_gps_review_groups.py:78."""
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "").strip()


def oracle_group_key(row: dict[str, Any]) -> str:
    """Verbatim ``group_key()`` from scripts/build_gps_review_groups.py:105."""
    return f"{oracle_norm(oracle_review_group_borough(row))}|{oracle_norm(oracle_review_group_location(row))}"


def oracle_stable_key(row: dict[str, Any]) -> str:
    """Verbatim ``stable_key()`` from scripts/build_gps_manual_approval_staging.py:73."""
    group_key = str(row.get("group_key") or "").strip().lower()
    if group_key:
        return f"group:{group_key}"
    return f"display:{oracle_norm_text(row.get('display_location'))}"


def oracle_row_location(row: dict[str, Any]) -> str:
    """Verbatim ``row_location()`` from
    scripts/generate_gps_staged_feed_integration_match_diagnostic.py:87
    (bit-identical copy at scripts/apply_gps_staged_feed_integration_update.py:54)."""
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "")


def oracle_event_cemsids(row: dict[str, Any]) -> set[str]:
    """Verbatim ``event_cemsids()`` from
    scripts/generate_gps_staged_feed_integration_match_diagnostic.py:265
    (bit-identical copy at scripts/apply_gps_staged_feed_integration_update.py:58).

    Restructured from the callers' set comprehension into an explicit loop to
    satisfy a SonarQube always-true-condition finding; semantics are identical
    (each item is converted with ``str()`` once and included only when the
    converted string is non-empty)."""
    raw = row.get("source_cemsid") or row.get("cemsid") or []
    if isinstance(raw, list):
        collected: set[str] = set()
        for item in raw:
            text = str(item)
            if text:
                collected.add(text)
        return collected
    if raw:
        return {str(raw)}
    return set()


def oracle_stable_event_identity(row: dict[str, Any]) -> str:
    """Verbatim ``stable_event_identity()`` from
    scripts/generate_gps_staged_feed_integration_match_diagnostic.py:274
    (bit-identical copy at scripts/apply_gps_staged_feed_integration_update.py:67)."""
    return "|".join(
        [
            str(row.get("source_event_id") or row.get("event_id") or row.get("id") or ""),
            oracle_norm_text(oracle_row_location(row)),
            ",".join(sorted(oracle_event_cemsids(row))),
            str(row.get("date") or ""),
            str(row.get("start_date_time") or ""),
        ]
    )


def oracle_split_ids(value: Any) -> list[str]:
    """Verbatim ``split_ids()`` from scripts/build_gps_repository.py:64."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def oracle_repository_date_key(row: dict[str, Any]) -> str:
    """Verbatim ``date_key()`` from scripts/build_gps_repository.py:79."""
    raw = str(row.get("date") or row.get("start_date_time") or row.get("start") or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def oracle_repository_location_text(row: dict[str, Any]) -> str:
    """Verbatim ``location_text()`` from scripts/build_gps_repository.py:85."""
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or row.get("address") or "").strip()


def oracle_repository_borough_text(row: dict[str, Any]) -> str:
    """Verbatim ``borough_text()`` from scripts/build_gps_repository.py:89."""
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def oracle_repository_title_text(row: dict[str, Any]) -> str:
    """Verbatim ``title_text()`` from scripts/build_gps_repository.py:93."""
    return str(row.get("title") or row.get("event_name") or row.get("name") or "").strip()


def oracle_repository_source_event_id(row: dict[str, Any]) -> str:
    """Verbatim ``source_event_id()`` from scripts/build_gps_repository.py:97."""
    return str(row.get("source_event_id") or row.get("event_id") or "").strip()


def oracle_candidate_keys(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Verbatim ``candidate_keys()`` from scripts/build_gps_repository.py:119."""
    keys: list[tuple[str, str]] = []
    event_id = oracle_repository_source_event_id(row)
    borough = oracle_repository_borough_text(row)
    location = oracle_repository_location_text(row)
    if event_id:
        keys.append((f"event_id:{event_id}", "event_id"))
    for cemsid in oracle_split_ids(row.get("source_cemsid") or row.get("cemsid")):
        keys.append((f"cemsid:{oracle_norm(borough)}:{cemsid}", "cemsid"))
    if location:
        keys.append((f"location:{oracle_norm(borough)}:{oracle_norm(location)}", "location"))
    if oracle_repository_title_text(row) and location and oracle_repository_date_key(row):
        keys.append((f"text_date_location:{oracle_norm(oracle_repository_title_text(row))}:{oracle_norm(borough)}:{oracle_norm(location)}:{oracle_repository_date_key(row)}", "text_date_location"))
    return keys


# ---------------------------------------------------------------------------
# Shared input matrices.
# ---------------------------------------------------------------------------

NORMALIZATION_VALUES: list[Any] = [
    "Prospect Park",
    "PROSPECT PARK",
    "  leading",
    "trailing  ",
    "  both  sides  ",
    "repeated    internal     spaces",
    "St. Mary's Church",
    "9th-Street / FDR: Drive, South",
    "Bryant Park & 42nd St.",
    "A&B&C",
    "&",
    " & ",
    "Café — «Le Parc»",
    "naïve résumé",
    "curly ‘quotes’ and “double”",
    "em—dash and en–dash",
    "ellipsis…here",
    "ÀÉÎÕÜ",
    "",
    "   ",
    None,
    0,
    5,
    -3,
    3.5,
    True,
    False,
    ["Central Park", "Sheep Meadow"],
    ("Tuple", "Value"),
]

ROW_MATRIX: list[dict[str, Any]] = [
    {
        "source_event_id": "EV-100",
        "event_id": "SHADOWED-1",
        "id": "SHADOWED-2",
        "title": "July 4th Fireworks",
        "borough": "Brooklyn",
        "display_location": "Prospect Park & 9th St.",
        "location": "shadowed",
        "event_location": "shadowed",
        "address": "95 Prospect Park West",
        "source_cemsid": ["CEM-2", "CEM-1"],
        "date": "2026-07-04",
        "start_date_time": "2026-07-04T20:00:00",
    },
    {"event_id": "EV-ONLY", "location": "Bryant Park", "borough": "Manhattan", "date": "2026-08-01"},
    {"id": "ID-ONLY", "event_location": "Flushing Meadows", "event_borough": "Queens", "start_date_time": "2026-09-01T09:30:00"},
    {"display_location": "No Borough Plaza"},
    {"borough": "Bronx"},
    {"borough": "Staten Island", "display_location": "St. George's — Pier 1 / Slip #3: Gate B, Rear"},
    {"borough": "MANHATTAN", "display_location": "M&M's World & Times Sq."},
    {"borough": "Queens", "display_location": "Café «Astoria» naïve"},
    {"borough": 11215, "display_location": 42},
    {"borough": 0, "display_location": False, "location": "Fallback Loc"},
    {"display_location": "   ", "borough": "Brooklyn", "title": "Whitespace Loc", "date": "2026-07-10"},
    {"display_location": "", "location": "", "event_location": "", "address": "Address Only Ave", "borough": "Bronx"},
    {"source_cemsid": "CEM-9,CEM-8, CEM-7", "borough": "Brooklyn", "display_location": "Comma Cemsids"},
    {"cemsid": ["  padded  ", "", "X1", "X1"], "display_location": "Cemsid List Edge"},
    {"source_cemsid": ["Z2", "A1", "A1", "M5"], "source_event_id": "EV-SORT", "display_location": "Sort Park", "date": "2026-07-04T10:00", "start_date_time": ""},
    {"source_cemsid": 12345, "display_location": "Numeric Cemsid"},
    {"group_key": "  Brooklyn|Prospect Park  ", "display_location": "ignored when group_key set"},
    {"group_key": "", "display_location": "Fallback & Display"},
    {"group_key": None, "display_location": None},
    {"title": "No Location Event", "borough": "Brooklyn", "date": "2026-07-15"},
    {"title": "No Date Event", "borough": "Brooklyn", "display_location": "Somewhere"},
    {"title": "Start-Only", "borough": "Queens", "display_location": "Elsewhere", "start": "2026-10-31T08:00:00"},
    {"title": "Bad Date", "borough": "Queens", "display_location": "Elsewhere", "date": "July 4, 2026"},
    {"event_name": "Event Name Fallback", "name": "shadowed", "borough": "Bronx", "display_location": "Fallback Fields", "date": "2026-11-11"},
    {"name": "Name Only Fallback", "borough": "Bronx", "display_location": "Name Field Row", "date": "2026-11-12"},
    {},
]


# ---------------------------------------------------------------------------
# A. Normalization profiles.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", NORMALIZATION_VALUES, ids=repr)
def test_normalize_text_legacy_matches_oracle(value: Any) -> None:
    assert normalize_text_legacy(value) == oracle_norm(value)


@pytest.mark.parametrize("value", NORMALIZATION_VALUES, ids=repr)
def test_normalize_text_with_ampersand_matches_oracle(value: Any) -> None:
    assert normalize_text_with_ampersand(value) == oracle_norm_text(value)


def test_normalization_golden_literals() -> None:
    """Anchor cases pinned as literals, independent of oracle and helper."""
    assert normalize_text_legacy("Bryant Park & 42nd St.") == "bryant park 42nd st"
    assert normalize_text_with_ampersand("Bryant Park & 42nd St.") == "bryant park and 42nd st"
    assert normalize_text_legacy("A&B&C") == "a b c"
    assert normalize_text_with_ampersand("A&B&C") == "a and b and c"
    assert normalize_text_legacy("  MiXeD   CaSe  ") == "mixed case"
    assert normalize_text_legacy("Café — «Le Parc»") == "caf le parc"
    assert normalize_text_with_ampersand("Café — «Le Parc»") == "caf le parc"
    assert normalize_text_legacy("St. Mary's Church") == "st mary s church"
    assert normalize_text_legacy("9th-Street / FDR: Drive, South") == "9th street fdr drive south"
    assert normalize_text_legacy(None) == ""
    assert normalize_text_legacy("") == ""
    assert normalize_text_legacy(0) == ""
    assert normalize_text_legacy(False) == ""
    assert normalize_text_legacy(True) == "true"
    assert normalize_text_legacy(5) == "5"
    assert normalize_text_with_ampersand(None) == ""
    assert normalize_text_with_ampersand(0) == ""
    assert normalize_text_with_ampersand(False) == ""
    assert normalize_text_with_ampersand(True) == "true"
    # Collection inputs pass through str() exactly as callers would today.
    assert normalize_text_legacy(["Central Park", "Sheep Meadow"]) == "central park sheep meadow"
    assert normalize_text_legacy(("Tuple", "Value")) == "tuple value"


def test_profiles_differ_only_on_ampersand() -> None:
    """The two active profiles must stay distinct: collapsing them would
    change persisted identity for any ampersand-bearing value."""
    assert normalize_text_legacy("A & B") == "a b"
    assert normalize_text_with_ampersand("A & B") == "a and b"
    assert normalize_text_legacy("Plain Text 42") == normalize_text_with_ampersand("Plain Text 42")


# ---------------------------------------------------------------------------
# B. Group key.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_build_group_key_matches_oracle(row: dict[str, Any]) -> None:
    assert build_group_key(row) == oracle_group_key(row)


def test_group_key_golden_literals() -> None:
    assert build_group_key({"borough": "Brooklyn", "display_location": "Prospect Park"}) == "brooklyn|prospect park"
    assert build_group_key({"display_location": "Prospect Park"}) == "|prospect park"
    assert build_group_key({"borough": "Brooklyn"}) == "brooklyn|"
    assert build_group_key({}) == "|"
    assert build_group_key({"borough": "Queens", "display_location": "M&M's World & Times Sq."}) == "queens|m m s world times sq"
    assert build_group_key({"event_borough": "Bronx", "event_location": "Café «Astoria»"}) == "bronx|caf astoria"
    assert build_group_key({"borough": 11215, "display_location": 42}) == "11215|42"
    # The grouping location accessor has NO address fallback.
    assert build_group_key({"borough": "Bronx", "address": "Address Only Ave"}) == "bronx|"


# ---------------------------------------------------------------------------
# C. Stable identity key (registry lineage).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_build_stable_identity_key_matches_oracle(row: dict[str, Any]) -> None:
    assert build_stable_identity_key(row) == oracle_stable_key(row)


def test_stable_identity_key_golden_literals() -> None:
    assert build_stable_identity_key({"group_key": "brooklyn|prospect park"}) == "group:brooklyn|prospect park"
    # group_key is stripped and lowercased but NOT re-normalized.
    assert build_stable_identity_key({"group_key": "  Brooklyn|Prospect Park  "}) == "group:brooklyn|prospect park"
    assert build_stable_identity_key({"group_key": "", "display_location": "Fallback & Display"}) == "display:fallback and display"
    assert build_stable_identity_key({"display_location": "Fallback & Display"}) == "display:fallback and display"
    assert build_stable_identity_key({}) == "display:"
    assert build_stable_identity_key({"group_key": None, "display_location": None}) == "display:"
    # Punctuation inside an existing group_key survives untouched.
    assert build_stable_identity_key({"group_key": "St. George's|Pier 1"}) == "group:st. george's|pier 1"


# ---------------------------------------------------------------------------
# D. Stable event identity (staged-feed lineage).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_build_stable_event_identity_matches_oracle(row: dict[str, Any]) -> None:
    assert build_stable_event_identity(row) == oracle_stable_event_identity(row)


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_row_location_matches_oracle(row: dict[str, Any]) -> None:
    assert row_location(row) == oracle_row_location(row)


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_event_cemsids_matches_oracle(row: dict[str, Any]) -> None:
    assert event_cemsids(row) == oracle_event_cemsids(row)


def test_stable_event_identity_golden_literals() -> None:
    assert build_stable_event_identity(
        {
            "source_event_id": "EV-100",
            "display_location": "Prospect Park & 9th St.",
            "source_cemsid": ["CEM-2", "CEM-1"],
            "date": "2026-07-04",
            "start_date_time": "2026-07-04T20:00:00",
        }
    ) == "EV-100|prospect park and 9th st|CEM-1,CEM-2|2026-07-04|2026-07-04T20:00:00"
    # id precedence: source_event_id > event_id > id.
    assert build_stable_event_identity({"event_id": "E2", "id": "E3"}).startswith("E2|")
    assert build_stable_event_identity({"id": "E3"}).startswith("E3|")
    # date is carried RAW (no truncation to a date key).
    assert build_stable_event_identity({"date": "2026-07-04T10:00"}) == "|||2026-07-04T10:00|"
    assert build_stable_event_identity({}) == "||||"
    # a comma-separated cemsid STRING is one identity component, not split.
    assert build_stable_event_identity({"source_cemsid": "C2,C1"}) == "||C2,C1||"


def test_event_cemsids_sonar_repair_falsy_and_duplicate_items() -> None:
    """Focused regression for the SonarQube always-true-condition repair:
    the loop form must keep the callers' exact semantics — items are included
    by the truthiness of their ``str()`` conversion, never of the raw item."""
    items = ["", None, 0, False, " ", "dup", "dup", "normal"]
    expected = {"None", "0", "False", " ", "dup", "normal"}
    row = {"source_cemsid": items}
    assert event_cemsids(row) == expected
    assert oracle_event_cemsids(row) == expected
    assert event_cemsids(row) == oracle_event_cemsids(row)
    # "" is excluded (str("") is empty); None/0/False are INCLUDED because
    # their str() forms are non-empty; " " is included (no stripping);
    # duplicates collapse via the set.
    assert build_stable_event_identity(row) == oracle_stable_event_identity(row)
    # input list unchanged
    assert items == ["", None, 0, False, " ", "dup", "dup", "normal"]


def test_event_cemsids_golden_behaviors() -> None:
    # list: no strip, empty strings dropped, duplicates collapse via set.
    assert event_cemsids({"source_cemsid": ["  padded  ", "", "X1", "X1"]}) == {"  padded  ", "X1"}
    # non-list truthy scalar becomes a one-element set.
    assert event_cemsids({"source_cemsid": 12345}) == {"12345"}
    # falsy values yield the empty set.
    assert event_cemsids({"source_cemsid": ""}) == set()
    assert event_cemsids({}) == set()
    # source_cemsid shadows cemsid.
    assert event_cemsids({"source_cemsid": ["A"], "cemsid": ["B"]}) == {"A"}


def test_row_location_preserves_no_strip_behavior() -> None:
    # Unlike the grouping/repository accessors, row_location does NOT strip.
    assert row_location({"display_location": "  Padded Park  "}) == "  Padded Park  "
    assert row_location({"display_location": "   "}) == "   "
    assert row_location({}) == ""
    # No address fallback in the staged-feed lineage.
    assert row_location({"address": "Address Only Ave"}) == ""


# ---------------------------------------------------------------------------
# E. Repository candidate keys.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("row", ROW_MATRIX, ids=lambda r: repr(sorted(r.keys())))
def test_build_repository_candidate_keys_matches_oracle(row: dict[str, Any]) -> None:
    assert build_repository_candidate_keys(row) == oracle_candidate_keys(row)


def test_candidate_keys_golden_literals() -> None:
    full = {
        "source_event_id": "EV-100",
        "title": "July 4th Fireworks",
        "borough": "Brooklyn",
        "display_location": "Prospect Park & 9th St.",
        "source_cemsid": "CEM-2, CEM-1",
        "date": "2026-07-04T20:00:00",
    }
    assert build_repository_candidate_keys(full) == [
        ("event_id:EV-100", "event_id"),
        ("cemsid:brooklyn:CEM-2", "cemsid"),
        ("cemsid:brooklyn:CEM-1", "cemsid"),
        ("location:brooklyn:prospect park 9th st", "location"),
        ("text_date_location:july 4th fireworks:brooklyn:prospect park 9th st:2026-07-04", "text_date_location"),
    ]
    # CEMSID values are NOT normalized; comma strings split in input order.
    # The legacy (non-ampersand) profile applies to the location component.
    assert build_repository_candidate_keys({"display_location": "A & B", "borough": "Queens"}) == [
        ("location:queens:a b", "location")
    ]
    # address is a valid 4th location fallback in this lineage only.
    assert build_repository_candidate_keys({"address": "Address Only Ave", "borough": "Bronx"}) == [
        ("location:bronx:address only ave", "location")
    ]
    # whitespace-only location strips to falsy: no location key emitted.
    assert build_repository_candidate_keys({"display_location": "   "}) == []
    # text_date_location requires title AND location AND a parseable date key.
    assert build_repository_candidate_keys({"title": "T", "display_location": "L", "date": "July 4, 2026"}) == [
        ("location::l", "location")
    ]
    assert build_repository_candidate_keys({}) == []


# ---------------------------------------------------------------------------
# F. Ordering independence.
# ---------------------------------------------------------------------------


def test_review_rank_never_affects_identity() -> None:
    base = {
        "source_event_id": "EV-100",
        "borough": "Brooklyn",
        "display_location": "Prospect Park",
        "group_key": "brooklyn|prospect park",
        "source_cemsid": ["C1"],
        "date": "2026-07-04",
        "title": "Fireworks",
    }
    with_rank_1 = {**base, "review_rank": 1}
    with_rank_99 = {**base, "review_rank": 99}
    for fn in (build_group_key, build_stable_identity_key, build_stable_event_identity, build_repository_candidate_keys):
        assert fn(with_rank_1) == fn(with_rank_99) == fn(base)


def test_review_rank_is_never_read() -> None:
    class KeyRecordingRow(dict):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.accessed: set[str] = set()

        def get(self, key: Any, default: Any = None) -> Any:
            self.accessed.add(key)
            return super().get(key, default)

    row = KeyRecordingRow(
        {
            "source_event_id": "EV-1",
            "borough": "Brooklyn",
            "display_location": "Prospect Park",
            "group_key": "",
            "review_rank": 7,
            "source_cemsid": ["C1"],
            "date": "2026-07-04",
            "start_date_time": "2026-07-04T10:00:00",
            "title": "Fireworks",
        }
    )
    build_group_key(row)
    build_stable_identity_key(row)
    build_stable_event_identity(row)
    build_repository_candidate_keys(row)
    row_location(row)
    event_cemsids(row)
    assert "review_rank" not in row.accessed


def test_source_cemsid_order_does_not_affect_stable_event_identity() -> None:
    row_a = {"source_event_id": "E", "source_cemsid": ["Z9", "A1", "M5"], "display_location": "Park"}
    row_b = {"source_event_id": "E", "source_cemsid": ["M5", "Z9", "A1"], "display_location": "Park"}
    assert build_stable_event_identity(row_a) == build_stable_event_identity(row_b)


def test_duplicate_cemsids_collapse() -> None:
    row_a = {"source_cemsid": ["A1", "A1", "A1", "B2"]}
    row_b = {"source_cemsid": ["B2", "A1"]}
    assert build_stable_event_identity(row_a) == build_stable_event_identity(row_b)


def test_row_order_and_unrelated_rows_do_not_affect_identity() -> None:
    rows = [dict(row) for row in ROW_MATRIX]
    forward = [build_stable_event_identity(row) for row in rows]
    backward = [build_stable_event_identity(row) for row in reversed(rows)]
    assert forward == list(reversed(backward))
    # Inserting unrelated rows between calls changes nothing (helpers hold no
    # cross-call state).
    interleaved = []
    for row in rows:
        build_stable_event_identity({"id": "UNRELATED", "display_location": "Elsewhere"})
        interleaved.append(build_stable_event_identity(row))
    assert interleaved == forward


def test_display_sorting_does_not_affect_identity() -> None:
    rows = [
        {"source_event_id": "B", "display_location": "Beta Park"},
        {"source_event_id": "A", "display_location": "Alpha Park"},
    ]
    identities_by_id = {row["source_event_id"]: build_stable_event_identity(row) for row in rows}
    sorted_rows = sorted(rows, key=lambda r: str(r["display_location"]))
    for row in sorted_rows:
        assert build_stable_event_identity(row) == identities_by_id[row["source_event_id"]]


# ---------------------------------------------------------------------------
# G. Side effects.
# ---------------------------------------------------------------------------


def test_inputs_are_never_mutated() -> None:
    for row in ROW_MATRIX:
        original = copy.deepcopy(row)
        build_group_key(row)
        build_stable_identity_key(row)
        build_stable_event_identity(row)
        build_repository_candidate_keys(row)
        row_location(row)
        event_cemsids(row)
        assert row == original, f"input row mutated: {row!r} != {original!r}"


def test_nested_lists_are_never_mutated() -> None:
    cemsids = ["Z2", "A1", "A1"]
    row = {"source_cemsid": cemsids, "display_location": "Park"}
    build_stable_event_identity(row)
    build_repository_candidate_keys(row)
    event_cemsids(row)
    assert cemsids == ["Z2", "A1", "A1"]


def test_module_has_no_io_network_time_or_env_dependencies() -> None:
    import scripts.gps_identity as gi

    source = Path(gi.__file__).read_text(encoding="utf-8")
    forbidden_imports = [
        "import os",
        "import sys",
        "import json",
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "import pathlib",
        "import datetime",
        "import time",
        "import random",
        "from os",
        "from pathlib",
        "from datetime",
        "subprocess",
        "os.environ",
        "getenv",
    ]
    for token in forbidden_imports:
        assert token not in source, f"forbidden dependency in gps_identity.py: {token}"
    module_globals = set(vars(gi))
    assert "open" not in module_globals
    assert {"re"} <= module_globals  # its only stdlib runtime import


def test_helpers_never_open_files_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked_open(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("gps_identity helper attempted file I/O")

    monkeypatch.setattr(builtins, "open", _blocked_open)
    for row in ROW_MATRIX:
        build_group_key(row)
        build_stable_identity_key(row)
        build_stable_event_identity(row)
        build_repository_candidate_keys(row)


def test_helpers_are_deterministic_across_repeated_calls() -> None:
    for row in ROW_MATRIX:
        first = (
            build_group_key(row),
            build_stable_identity_key(row),
            build_stable_event_identity(row),
            build_repository_candidate_keys(row),
        )
        for _ in range(3):
            assert (
                build_group_key(row),
                build_stable_identity_key(row),
                build_stable_event_identity(row),
                build_repository_candidate_keys(row),
            ) == first


# ---------------------------------------------------------------------------
# H. Separation from historical and fixture-only identity systems, plus the
#    M7-B caller migration boundary.
# ---------------------------------------------------------------------------


def test_helper_module_does_not_touch_tools_registry() -> None:
    import scripts.gps_identity as gi

    source = Path(gi.__file__).read_text(encoding="utf-8")
    assert "tools" not in [line.split()[1].split(".")[0] for line in source.splitlines() if line.startswith(("import ", "from "))]


def test_fixture_only_clean_text_vocabulary_unchanged_and_distinct() -> None:
    from tools.registry.xri_g41_fixture_only_parser_normalizer import _clean_text

    # xri_g41's normalization neither case-folds nor strips punctuation —
    # the fixture-only vocabulary is intentionally weaker and separate.
    value = "  Prospect   Park &  9th St.  "
    assert _clean_text(value) == "Prospect Park & 9th St."
    assert _clean_text(value) != normalize_text_legacy(value)
    assert _clean_text(value) != normalize_text_with_ampersand(value)


def test_historical_xri_g7_hashing_behavior_unchanged() -> None:
    from tools.registry.xri_g7_fixture_candidate_normalizer import candidate_identity_key, slug

    assert slug("A & B") == "a-b"  # dash-separated, distinct from both active profiles
    record = {
        "source_dataset_id": "tvpk-puvk",
        "source_record_id": "REC-77",
        "title": "Prospect Park & 9th St. Fair",
        "event_start": "2026-07-04T10:00:00",
        "location_text": "Prospect Park West",
    }
    # Golden literal captured from the committed implementation at the M7-A
    # baseline (8796d64). Any change to historical hashing breaks this.
    assert candidate_identity_key(record) == "xri-g7:tvpk-puvk:fd36d36de1a31946"


ACTIVE_CALLER_FILES = [
    "scripts/build_gps_repository.py",
    "scripts/build_gps_review_groups.py",
    "scripts/build_gps_geocoding_filled_proposals.py",
    "scripts/build_gps_manual_approval_staging.py",
    "scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
    "scripts/apply_gps_staged_feed_integration_update.py",
]

M7B_MIGRATED_CALLER_IMPORTS = {
    "scripts/build_gps_repository.py": ["build_repository_candidate_keys"],
    "scripts/build_gps_review_groups.py": ["build_group_key"],
    "scripts/build_gps_geocoding_filled_proposals.py": ["normalize_text_legacy"],
    "scripts/build_gps_manual_approval_staging.py": ["build_stable_identity_key", "normalize_text_with_ampersand"],
    "scripts/generate_gps_staged_feed_integration_match_diagnostic.py": [
        "build_stable_event_identity",
        "event_cemsids",
        "normalize_text_with_ampersand",
        "row_location",
    ],
    "scripts/apply_gps_staged_feed_integration_update.py": [
        "build_stable_event_identity",
        "event_cemsids",
        "row_location",
    ],
    "scripts/audit_feed_anomalies.py": ["normalize_text_legacy"],
    "scripts/audit_row_disposition.py": ["normalize_text_legacy"],
    "scripts/build_location_cache.py": ["normalize_text_legacy"],
    "scripts/build_staged_production_feed.py": ["normalize_text_legacy"],
    "scripts/build_test_enriched_feed.py": ["normalize_text_legacy"],
    "scripts/sync_nyc_open_data.py": ["normalize_text_legacy"],
}


def test_m7b_authorized_callers_import_shared_gps_identity_helper() -> None:
    """M7-B deliberately migrates the documented active callers to
    scripts.gps_identity while keeping historical xri helpers separate."""
    assert set(ACTIVE_CALLER_FILES) <= set(M7B_MIGRATED_CALLER_IMPORTS)
    for rel_path, helper_names in M7B_MIGRATED_CALLER_IMPORTS.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "from scripts.gps_identity import" in source, f"{rel_path} does not import the shared helper"
        for helper_name in helper_names:
            assert helper_name in source, f"{rel_path} does not reference {helper_name}"


def test_m7b_removes_documented_active_duplicate_identity_functions() -> None:
    """M7-B removes only the duplicated active-pipeline identity helpers."""
    expectations = {
        "scripts/build_gps_repository.py": ["def norm(", "def candidate_keys("],
        "scripts/build_gps_review_groups.py": ["def norm(", "def group_key("],
        "scripts/build_gps_geocoding_filled_proposals.py": ["def norm("],
        "scripts/build_gps_manual_approval_staging.py": ["def norm_text(", "def stable_key("],
        "scripts/generate_gps_staged_feed_integration_match_diagnostic.py": [
            "def normalize(",
            "def row_location(",
            "def event_cemsids(",
            "def stable_event_identity(",
        ],
        "scripts/apply_gps_staged_feed_integration_update.py": [
            "def normalize(",
            "def row_location(",
            "def event_cemsids(",
            "def stable_event_identity(",
        ],
        "scripts/audit_feed_anomalies.py": ["def norm("],
        "scripts/audit_row_disposition.py": ["def norm("],
        "scripts/build_location_cache.py": ["def norm("],
        "scripts/build_staged_production_feed.py": ["def norm("],
        "scripts/build_test_enriched_feed.py": ["def norm("],
        "scripts/sync_nyc_open_data.py": ["def norm("],
    }
    for rel_path, needles in expectations.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in source, f"{rel_path} still contains duplicated helper {needle}"


def test_m7b_callers_bind_to_the_canonical_helper_functions() -> None:
    import scripts.gps_identity as gi

    repo = importlib.import_module("scripts.build_gps_repository")
    groups = importlib.import_module("scripts.build_gps_review_groups")
    geocoding = importlib.import_module("scripts.build_gps_geocoding_filled_proposals")
    manual = importlib.import_module("scripts.build_gps_manual_approval_staging")
    diagnostic = importlib.import_module("scripts.generate_gps_staged_feed_integration_match_diagnostic")
    update = importlib.import_module("scripts.apply_gps_staged_feed_integration_update")

    assert repo.build_repository_candidate_keys is gi.build_repository_candidate_keys
    assert groups.build_group_key is gi.build_group_key
    assert geocoding.normalize_text_legacy is gi.normalize_text_legacy
    assert manual.build_stable_identity_key is gi.build_stable_identity_key
    assert manual.normalize_text_with_ampersand is gi.normalize_text_with_ampersand
    assert diagnostic.stable_event_identity is gi.build_stable_event_identity
    assert diagnostic.row_location is gi.row_location
    assert diagnostic.event_cemsids is gi.event_cemsids
    assert update.stable_event_identity is gi.build_stable_event_identity
    assert update.row_location is gi.row_location
    assert update.event_cemsids is gi.event_cemsids


def test_m7b_legacy_norm_callers_bind_to_legacy_normalizer() -> None:
    module_names = [
        "scripts.audit_feed_anomalies",
        "scripts.audit_row_disposition",
        "scripts.build_location_cache",
        "scripts.build_staged_production_feed",
        "scripts.build_test_enriched_feed",
        "scripts.sync_nyc_open_data",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        assert module.normalize_text_legacy is normalize_text_legacy
        assert module.normalize_text_legacy("Bryant Park & 42nd St.") == oracle_norm("Bryant Park & 42nd St.")


def test_m7b_repository_add_entries_uses_helper_keys_bit_for_bit() -> None:
    repo = importlib.import_module("scripts.build_gps_repository")
    row = {
        "source_event_id": "EV-100",
        "title": "July 4th Fireworks",
        "borough": "Brooklyn",
        "display_location": "Prospect Park & 9th St.",
        "source_cemsid": "CEM-2, CEM-1",
        "date": "2026-07-04T20:00:00",
        "lat": 40.6602,
        "lng": -73.9690,
        "review_rank": 999,
    }
    expected_pairs = build_repository_candidate_keys(row)
    cache: dict[str, Any] = {}

    rows_with_gps, added = repo.add_entries(cache, [row], "unit_test")

    assert rows_with_gps == 1
    assert added == len(expected_pairs)
    assert list(cache) == [key for key, _key_type in expected_pairs]
    assert [cache[key]["key_type"] for key in cache] == [key_type for _key, key_type in expected_pairs]


def test_m7b_manual_staging_candidate_identity_uses_helper_and_not_review_rank() -> None:
    manual = importlib.import_module("scripts.build_gps_manual_approval_staging")
    base = {
        "group_key": "",
        "display_location": "Baisley Pond Park & Playground",
        "proposed_lat": 40.672,
        "proposed_lng": -73.785,
    }
    candidate_a = manual.make_candidate({**base, "review_rank": 1}, "unit")
    candidate_b = manual.make_candidate({**base, "review_rank": 42}, "unit")

    assert candidate_a["stable_identity_key"] == build_stable_identity_key(base)
    assert candidate_b["stable_identity_key"] == build_stable_identity_key(base)
    assert candidate_a["stable_identity_key"] == candidate_b["stable_identity_key"]


def test_m7b_staged_feed_callers_preserve_cemsid_order_and_review_rank_independence() -> None:
    diagnostic = importlib.import_module("scripts.generate_gps_staged_feed_integration_match_diagnostic")
    update = importlib.import_module("scripts.apply_gps_staged_feed_integration_update")
    row_a = {
        "source_event_id": "EV-100",
        "display_location": "Prospect Park & 9th St.",
        "source_cemsid": ["Z9", "A1", "M5"],
        "date": "2026-07-04",
        "start_date_time": "2026-07-04T20:00:00",
        "review_rank": 1,
    }
    row_b = {**row_a, "source_cemsid": ["M5", "Z9", "A1"], "review_rank": 99}
    expected = build_stable_event_identity(row_a)

    assert expected == build_stable_event_identity(row_b)
    assert diagnostic.stable_event_identity(row_a) == expected
    assert diagnostic.stable_event_identity(row_b) == expected
    assert update.stable_event_identity(row_a) == expected
    assert update.stable_event_identity(row_b) == expected


# ---------------------------------------------------------------------------
# I. Golden compatibility result: zero unexplained identity changes.
# ---------------------------------------------------------------------------


def test_zero_identity_changes_across_full_matrix() -> None:
    """Every identity builder must agree with its caller-source oracle on
    every matrix row. Any mismatch is reported as a changed input/output pair
    and constitutes a blocking M7-A failure."""
    changed_pairs: list[dict[str, Any]] = []
    for index, row in enumerate(ROW_MATRIX):
        checks = [
            ("group_key", build_group_key(row), oracle_group_key(row)),
            ("stable_identity_key", build_stable_identity_key(row), oracle_stable_key(row)),
            ("stable_event_identity", build_stable_event_identity(row), oracle_stable_event_identity(row)),
            ("repository_candidate_keys", build_repository_candidate_keys(row), oracle_candidate_keys(row)),
        ]
        for name, actual, expected in checks:
            if actual != expected:
                changed_pairs.append({"row_index": index, "row": row, "identity": name, "helper": actual, "oracle": expected})
    assert changed_pairs == [], f"unexplained identity changes: {changed_pairs!r}"
