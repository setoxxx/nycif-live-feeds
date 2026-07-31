import csv, json, sqlite3, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from nyc_event_atlas.dedupe import occurrence_key
from nyc_event_atlas.schema import EXPORT_COLUMNS

root=Path(__file__).resolve().parents[1]
path=Path(sys.argv[1])
with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
if list(rows[0]) != EXPORT_COLUMNS: raise SystemExit('Schema mismatch')
with sqlite3.connect(root/'data'/'atlas.sqlite') as conn:
    now=datetime.now(timezone.utc).isoformat()
    for r in rows:
        conn.execute('INSERT OR IGNORE INTO event_series(series_id,canonical_name,organizer,first_seen_at,last_verified_at) VALUES(?,?,?,?,?)',(r['SERIES_ID'],r['EVENT_NAME'],r['ORGANIZER'],now,r['LAST_VERIFIED']))
        conn.execute('INSERT OR IGNORE INTO events(event_id,series_id,record_json,occurrence_key,created_at,updated_at) VALUES(?,?,?,?,?,?)',(r['EVENT_ID'],r['SERIES_ID'],json.dumps(r,ensure_ascii=False),occurrence_key(r),now,now))
print(f'imported {len(rows)} rows')
