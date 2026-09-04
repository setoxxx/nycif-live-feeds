from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260904170500_native_map_feed_window.sql"
EDGE_FN = ROOT / "supabase/functions/nycif-native-map-feed/index.ts"


def test_feed_window_sql_is_read_only():
    sql = MIGRATION.read_text()
    assert "nycif_native_map_feed_rows" in sql
    assert "nycif_native_map_feed_stats" in sql
    assert "start_at < m.start_before" in sql
    assert "tomorrow_start" in sql
    assert "seven_end" in sql
    lowered = sql.lower()
    for banned in (
        "insert into public.event_occurrences",
        "update public.event_occurrences",
        "delete from public.event_occurrences",
        "location_cache",
        "promotion_allowed",
        "p_allow_expire",
    ):
        assert banned not in lowered
    assert "grant execute on function public.nycif_native_map_feed_rows(text) to service_role" in lowered
    assert "revoke all on function public.nycif_native_map_feed_rows(text) from anon" in lowered


def test_edge_function_uses_window_rpc_not_paged_view():
    source = EDGE_FN.read_text()
    assert 'db.rpc("nycif_native_map_feed_rows"' in source
    assert 'db.rpc("nycif_native_map_feed_stats")' in source
    assert "event_reader_rolling_v1" not in source or "authority" in source
    assert ".from(\"event_reader_rolling_v1\")" not in source
    assert "for (let from = 0; from < 20000" not in source
    assert "certified_pin === true" in source
    assert "native_map_feed_unavailable" in source
    assert 'schema_version: "NYCIF_NATIVE_MAP_FEED_V3"' in source
    assert "latitude: mapped ? Number(row.lat) : null" in source
