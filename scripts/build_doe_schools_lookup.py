#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup,socrata_rows,write_lookup

def aliases(name,row):
    values={name}; code=row.get('ats_system_code') or row.get('location_code') or row.get('dbn')
    if code: values.add(str(code))
    return values

def main():
    rows=[]; source='jfju-ynrr'
    try: rows=socrata_rows('3bkj-34v2',order='school_name')
    except Exception as exc: print(f'DOE source unavailable: {type(exc).__name__}: {exc}')
    payload=build_lookup(rows,dataset_id=source,name_fields=('school_name','location_name','schoolname','name'),id_fields=('ats_system_code','location_code','dbn'),borough_fields=('borough','boro'),facility_type='school',geometry_fields=('the_geom','point'),alias_expander=aliases)
    payload['metadata']['source_view']='3bkj-34v2'; payload['metadata']['requested_file_asset']='jfju-ynrr'; payload['metadata']['source_available']=bool(rows)
    write_lookup(payload,ROOT/'data/doe_school_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
