#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,fetch_json,write_lookup
URL='https://www.bklynlibrary.org/locations/json'
def rows_from_payload(payload):
    if isinstance(payload,list): return payload
    if isinstance(payload,dict):
        for key in ('locations','branches','data'):
            if isinstance(payload.get(key),list): return payload[key]
    return []
def aliases(name,row): return {name,f'{name} Library',f'Brooklyn Public Library - {name}',f'BPL- {name}',f'BPL {name} Library'}
def main():
    try: rows=rows_from_payload(fetch_json(URL))
    except Exception as exc:
        rows=[]; print(f'official BPL href unavailable: {type(exc).__name__}: {exc}')
    normalized=[]
    for row in rows:
        if not isinstance(row,dict): continue
        item=dict(row); item['name']=row.get('name') or row.get('title') or row.get('branch'); item['latitude']=row.get('latitude') or row.get('lat'); item['longitude']=row.get('longitude') or row.get('lng') or row.get('lon'); item['borough']='Brooklyn'; item['authority_id']=row.get('id') or row.get('slug') or row.get('url'); normalized.append(item)
    payload=build_lookup(normalized,dataset_id='xmzf-uf2w',name_fields=('name',),id_fields=('authority_id',),borough_fields=('borough',),facility_type='library',alias_expander=aliases)
    payload['metadata']['official_href_target']=URL; payload['metadata']['source_available']=bool(rows)
    write_lookup(payload,ROOT/'data/library_brooklyn_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
