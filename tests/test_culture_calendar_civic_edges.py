"""Fail-closed checks for Culture calendar / civic edge readers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALENDAR_TS = ROOT / "supabase" / "functions" / "nycif-culture-calendar" / "index.ts"
CIVIC_TS = ROOT / "supabase" / "functions" / "nycif-culture-civic" / "index.ts"
LIVE_SQL = ROOT / "supabase" / "migrations" / "20260906154500_culture_calendar_civic_live_v1.sql"
SCAFFOLD_SQL = ROOT / "supabase" / "migrations" / "20260906050000_culture_community_scaffold_v1.sql"


def test_edge_entrypoints_exist():
    assert CALENDAR_TS.is_file()
    assert CIVIC_TS.is_file()


def test_calendar_contract_keys():
    source = CALENDAR_TS.read_text(encoding="utf-8")
    for token in (
        "authority: \"nycif-culture-calendar\"",
        "schema_version: SCHEMA_VERSION",
        "culture-calendar-v1",
        "calendar_publication_enabled",
        "help_calendar_publication_enabled",
        "blood_layer_enabled",
        "occurrences:",
        'eq("id", "v1")',
        "GET,HEAD,OPTIONS",
    ):
        assert token in source, token
    assert "business_publication_enabled" not in source


def test_civic_contract_keys():
    source = CIVIC_TS.read_text(encoding="utf-8")
    for token in (
        "authority: \"nycif-culture-civic\"",
        "culture-civic-v1",
        "civic_publication_enabled",
        "pet_care_layer_enabled",
        "features:",
        'eq("id", "v1")',
        "GET,HEAD,OPTIONS",
    ):
        assert token in source, token
    assert "business_publication_enabled" not in source


def test_live_sql_does_not_flip_storefronts_or_use_numeric_id():
    sql = LIVE_SQL.read_text(encoding="utf-8")
    assert "calendar_publication_enabled boolean not null default false" in sql
    assert "civic_publication_enabled boolean not null default false" in sql
    assert "help_calendar_publication_enabled boolean not null default false" in sql
    assert "create table if not exists public.culture_calendar_occurrence_v1" in sql
    assert "create table if not exists public.culture_civic_facility_v1" in sql
    assert "enable row level security" in sql
    assert "where id = 'v1'" in sql
    assert "business_publication_enabled =" not in sql
    assert "alter table public.culture_place_beta_v1" not in sql
    assert "insert into public.culture_reader_settings" not in sql


def test_draft_scaffold_stays_numeric_and_is_not_the_live_apply():
    sql = SCAFFOLD_SQL.read_text(encoding="utf-8")
    assert "values (1)" in sql
    assert "Do not apply to production until a human confirms" in sql
