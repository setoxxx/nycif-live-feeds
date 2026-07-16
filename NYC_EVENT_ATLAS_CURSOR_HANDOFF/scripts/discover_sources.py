import json, yaml
from pathlib import Path
from nyc_event_atlas.source_discovery import discover
cfg=yaml.safe_load(Path('config/sources.yaml').read_text())
reports=[]
for s in cfg['sources']:
    url=s.get('url')
    if not url: continue
    try: reports.append({'source_id':s['id'],'result':discover(url)})
    except Exception as e: reports.append({'source_id':s['id'],'error':str(e)})
Path('logs/source_discovery.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print('logs/source_discovery.json')
