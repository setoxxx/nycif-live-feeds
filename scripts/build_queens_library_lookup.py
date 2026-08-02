#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,socrata_rows,write_lookup

def aliases(name,row): return {name,f'{name} Library',f'Queens Public Library - {name}',f'QPL {name} Library'}
def main():
    rows=socrata_rows('kh3d-xhq7',order='name')
    payload=build_lookup(rows,dataset_id='kh3d-xhq7',name_fields=('name',),id_fields=('bin','bbl','hours_can_be_viewed_via_branch_url_'),borough_fields=('borough',),facility_type='library',geometry_fields=('point',),alias_expander=aliases)
    write_lookup(payload,ROOT/'data/library_queens_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
