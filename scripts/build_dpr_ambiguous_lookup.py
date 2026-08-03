#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.park_geometry import build_park_lookup,load_parks_properties,normalize_park_name,DATASET_URL

def main():
    rows=load_parks_properties(DATASET_URL); grouped=defaultdict(list)
    for row in rows:
        park_id=str(row.get('gispropnum') or '').strip()
        if park_id: grouped[park_id].append(row)
    aliases=defaultdict(dict)
    for park_id in sorted(grouped):
        result=build_park_lookup(grouped[park_id])
        if not result.lookup: continue
        entry=next(iter(result.lookup.values()))
        for row in grouped[park_id]:
            for field in ('signname','name311','propertyname','location','name'):
                key=normalize_park_name(row.get(field))
                if len(key)>=3: aliases[key][park_id]=entry
    ambiguous={alias:sorted(values.values(),key=lambda x:str(x.get('park_id'))) for alias,values in sorted(aliases.items()) if len(values)>1}
    path=ROOT/'data/park_ambiguous_candidates.json'; path.write_text(json.dumps({'metadata':{'source_dataset':'enfh-gkve','ambiguous_aliases':len(ambiguous),'promotion_allowed':False},'aliases':ambiguous},indent=2,sort_keys=True)+'\n')
    print({'ambiguous_aliases':len(ambiguous)})
if __name__=='__main__': main()
