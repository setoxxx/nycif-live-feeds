#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import load_lookup,write_lookup
SOURCES=('library_citywide_centroids.json','library_queens_centroids.json','library_brooklyn_centroids.json')
def main():
    candidates={}; ambiguous=set(); source_meta=[]
    for filename in SOURCES:
        payload=load_lookup(ROOT/'data'/filename); source_meta.append(payload.get('metadata') or {}); ambiguous.update(payload.get('ambiguous_aliases') or [])
        for alias,entry in (payload.get('aliases') or {}).items(): candidates.setdefault(alias,{})[str(entry.get('authority_id'))]=entry
    aliases={}
    for alias in sorted(candidates):
        values=list(candidates[alias].values()); unique={(v.get('facility_name'),v.get('borough'),v.get('lat'),v.get('lng')):v for v in values}
        if len(unique)==1 and alias not in ambiguous: aliases[alias]=next(iter(unique.values()))
        else: ambiguous.add(alias)
    ids={v.get('authority_id') for v in aliases.values()}
    payload={'metadata':{'source_datasets':['feuq-due4','kh3d-xhq7','xmzf-uf2w'],'source_rows':sum(int(m.get('source_rows',0)) for m in source_meta),'valid_geometry_rows':sum(int(m.get('valid_geometry_rows',0)) for m in source_meta),'unique_facilities':len(ids),'aliases_written':len(aliases),'ambiguous_aliases_omitted':len(ambiguous),'float_precision':7,'promotion_allowed':False},'aliases':aliases,'ambiguous_aliases':sorted(ambiguous)}
    write_lookup(payload,ROOT/'data/library_branch_centroids.json'); print(payload['metadata'])
if __name__=='__main__': main()
