#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,socrata_rows,write_lookup

def aliases(name,row):
    system=str(row.get('system') or '').upper(); return {name,f'{name} Library',f'{system} - {name}',f'{system} {name} Library'}
def main():
    rows=socrata_rows('feuq-due4',order='system,name')
    payload=build_lookup(rows,dataset_id='feuq-due4',name_fields=('name',),id_fields=('bin','bbl','url'),borough_fields=('borocode','city'),facility_type='library',geometry_fields=('the_geom',),alias_expander=aliases)
    write_lookup(payload,ROOT/'data/library_citywide_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
