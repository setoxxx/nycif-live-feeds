from pathlib import Path
import sqlite3
root=Path(__file__).resolve().parents[1]
db=root/'data'/'atlas.sqlite'
sql=(root/'sql'/'schema.sql').read_text(encoding='utf-8')
with sqlite3.connect(db) as conn: conn.executescript(sql)
print(db)
