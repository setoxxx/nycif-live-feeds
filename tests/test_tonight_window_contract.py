from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260906043000_tonight_starts_5pm.sql"
EDGE = ROOT / "supabase/functions/nycif-native-map-feed/index.ts"
CONTRACT = ROOT / "docs/contracts/TONIGHT_WINDOW_AND_NIGHT_LAYERS.md"


def test_sql_tonight_starts_at_5pm_not_6pm():
    sql = MIGRATION.read_text()
    assert "interval '17 hours'" in sql
    assert "interval '18 hours'" not in sql
    assert "m.mode = 'tonight'" in sql
    assert "eo.start_at >= m.window_start" in sql
    assert "Do not use overlap for" in sql or "Not an overlap window" in sql


def test_edge_function_reads_sql_tonight_and_exposes_night_layer_urls():
    source = EDGE.read_text()
    assert 'start: "17:00:00"' in source
    assert 'start: "18:00:00"' not in source
    assert '{ p_mode: "tonight" }' in source
    assert "startMinute" not in source
    assert "18 * 60" not in source
    assert "nycif-night-layers" in source
    assert "?layer=" in source
    assert 'id: "dispensary"' in source
    assert 'id: "liquor"' in source
    assert 'id: "5pm"' in source
    assert "SUPABASE_SERVICE_ROLE_KEY" in source
    assert "NYCIF_NATIVE_MAP_FEED_V6" in source


def test_contract_keeps_layers_off_the_event_corpus():
    text = CONTRACT.read_text()
    assert "17:00:00" in text
    assert "service_role" in text
    assert "not `event_occurrences`" in text or "not event_occurrences" in text.lower()
    assert "nycif-night-layers?layer=dispensary" in text
    assert "nycif-night-layers?layer=liquor" in text
