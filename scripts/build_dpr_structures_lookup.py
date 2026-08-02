#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from nycif.normalize.facility_lookup import build_lookup, socrata_rows, write_lookup

def facility_type(row):
    text=str(row.get('description') or '').casefold()
    if row.get('recreation_center') is True or str(row.get('recreation_center')).casefold()=='true': return 'recreation_center'
    for term, kind in [('nature center','nature_center'),('visitor center','visitor_center'),('audubon center','nature_center'),('boathouse','boathouse'),('field house','field_house')]:
        if term in text: return kind
    return 'park_structure'

def aliases(name,row):
    values={name}
    values.add(re.sub(r"\b(?:building|men's public restroom|women's public restroom|public restroom)\b",'',name,flags=re.I).strip(' -'))
    if row.get('location'): values.add(str(row['location']))
    return values

def main():
    rows=socrata_rows('n8q6-i44s',order='borough,gispropnum,system')
    payloads=[]
    for kind in ('recreation_center','nature_center','visitor_center','boathouse','field_house','park_structure'):
        payloads.append(build_lookup(rows,dataset_id='n8q6-i44s',name_fields=('description',),id_fields=('system','doitt_id','omppropid'),borough_fields=('borough',),facility_type=kind,geometry_fields=('multipolygon',),alias_expander=aliases,row_filter=lambda row,k=kind: facility_type(row)==k))
    aliases_out={}; ambiguous=set(); meta={'source_dataset':'n8q6-i44s','source_rows':len(rows),'valid_geometry_rows':0,'unique_facilities':0,'aliases_written':0,'ambiguous_aliases_omitted':0,'float_precision':7,'promotion_allowed':False}
    ids=set(); candidates={}
    for payload in payloads:
        meta['valid_geometry_rows']+=payload['metadata']['valid_geometry_rows']; ids.update(e['authority_id'] for e in payload['aliases'].values())
        for alias,entry in payload['aliases'].items(): candidates.setdefault(alias,{})[entry['authority_id']]=entry
        ambiguous.update(payload['ambiguous_aliases'])
    for alias in sorted(candidates):
        vals=list(candidates[alias].values())
        if len(vals)==1 and alias not in ambiguous: aliases_out[alias]=vals[0]
        else: ambiguous.add(alias)
    meta.update(unique_facilities=len(ids),aliases_written=len(aliases_out),ambiguous_aliases_omitted=len(ambiguous))
    write_lookup({'metadata':meta,'aliases':aliases_out,'ambiguous_aliases':sorted(ambiguous)},ROOT/'data/dpr_structures_centroids.json')
    print(meta)
if __name__=='__main__': main()
