#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,socrata_rows,write_lookup

def aliases(name,row): return {name, str(row.get('address') or '')}
def main():
    rows=socrata_rows('67g2-p84d',order='boro,facname,uid')
    payload=build_lookup(rows,dataset_id='2fpa-bnsx',name_fields=('facname',),id_fields=('uid',),borough_fields=('boro','borocode'),facility_type='dcp_cross_check',alias_expander=aliases)
    payload['metadata']['data_view']='67g2-p84d'; payload['metadata']['primary_matcher']=False
    write_lookup(payload,ROOT/'data/dcp_facility_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
