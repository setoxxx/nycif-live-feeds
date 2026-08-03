#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,socrata_rows,write_lookup

def aliases(name,row): return {name, name.replace(' Wading Pool',' Pool'), f"{name} in {name} and Park"}
def main():
    rows=socrata_rows('y5rm-wagw',order='borough,gispropnum,system')
    payload=build_lookup(rows,dataset_id='y5rm-wagw',name_fields=('name',),id_fields=('system','omppropid'),borough_fields=('borough',),facility_type='pool',geometry_fields=('polygon',),alias_expander=aliases)
    write_lookup(payload,ROOT/'data/dpr_pool_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
