#!/usr/bin/env python3
"""Project staged + supplemental feeds into schema_version 1.0 envelopes."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from enigma.shadow2.location_evidence import classify_location_evidence
from nycif.normalize.facility_resolver import resolve_facility_anchor
from nycif.normalize.facility_resolvers import resolve_authoritative_facility
from nycif.normalize.facility_resolvers.park_ambiguity_resolver import resolve_borough_qualified_park
from nycif.normalize.park_geometry import load_park_lookup
from schema_v1_common import SCHEMA_VERSION,envelope,extract_events,project_event,reset_stable_id_registry,write_repo_json,utc_now
STAGED_PATH=ROOT/'data/nycif_staged_live_events.json'; SUPPLEMENTAL_PATH=ROOT/'data/supplemental_events_staging_feed.json'; OUT_REPORT=ROOT/'data/events_schema_v1_validation_report.json'
REQUIRED_EVENT_FIELDS=['id','title','category','start_date_time','end_date_time','timezone','borough','location','latitude','longitude','significance','source']

def validate_event(event,errors,prefix):
    for key in REQUIRED_EVENT_FIELDS:
        if key not in event: errors.append(f'{prefix}: missing field {key}')
    source=event.get('source')
    if not isinstance(source,dict) or 'dataset' not in source or 'source_event_id' not in source: errors.append(f'{prefix}: source must include dataset and source_event_id')
    lat,lng=event.get('latitude'),event.get('longitude')
    if (lat is None)!=(lng is None): errors.append(f'{prefix}: latitude/longitude must both be set or both null')
    if 'lat' in event or 'lng' in event: errors.append(f'{prefix}: legacy lat/lng leaked')
    nycif=event.get('nycif') or {}
    if nycif.get('data_layer')!='review_supplemental': return
    if nycif.get('promotion_allowed') is True: errors.append(f'{prefix}: supplemental promotion_allowed true')
    if nycif.get('production_feed') is True: errors.append(f'{prefix}: supplemental production_feed true')
    if not str(event.get('id','')).startswith('review_supplemental:'): errors.append(f'{prefix}: supplemental id not namespaced')
    if nycif.get('coordinate_status')=='approximate':
        if nycif.get('display_disposition')!='approximate_marker': errors.append(f'{prefix}: approximate lacks approximate_marker')
        if nycif.get('coordinate_precision') not in {'park_level_anchor','certified_facility'}: errors.append(f'{prefix}: unexpected approximate precision')
        expected={'park_level_anchor':{'dpr_parks_properties_centroid'},'certified_facility':{'dpr_parks_structures_centroid','nyc_library_branches_centroid','doe_school_points_centroid','dpr_pools_centroid'}}
        if nycif.get('coordinate_source') not in expected.get(nycif.get('coordinate_precision'),set()): errors.append(f'{prefix}: unexpected coordinate source')
        if lat is None or lng is None: errors.append(f'{prefix}: approximate lacks coordinate pair')

def _probe(projected,source_row):
    probe=dict(source_row); probe['evidence_tier']='unresolved'; probe['location']=projected.get('location') or source_row.get('location'); probe['borough']=projected.get('borough') or source_row.get('borough') or source_row.get('event_borough'); return probe

def apply_supplemental_anchor(projected:dict[str,Any],source_row:dict[str,Any],*,park_lookup):
    nycif=projected.get('nycif') if isinstance(projected.get('nycif'),dict) else {}
    if nycif.get('data_layer')!='review_supplemental' or nycif.get('coordinate_status')!='list_only': return projected
    try: tier=classify_location_evidence(projected).tier.value
    except Exception: return projected
    if tier!='unresolved': return projected
    probe=_probe(projected,source_row)
    resolved=resolve_facility_anchor(probe,lookup=park_lookup)
    if not resolved: resolved=resolve_borough_qualified_park(probe)
    if not resolved: resolved=resolve_authoritative_facility(probe)
    if not resolved: return projected
    projected['latitude']=resolved['latitude']; projected['longitude']=resolved['longitude']
    nycif=dict(nycif); nycif.update({k:v for k,v in resolved.items() if k not in {'latitude','longitude'}})
    nycif.update({'coordinate_status':'approximate','display_disposition':'approximate_marker','promotion_allowed':False,'production_feed':False,'public_map_modified':False})
    projected['nycif']=nycif; return projected

def project_layer(rows,*,data_layer,park_lookup=None):
    reset_stable_id_registry(); output=[]; lookup=park_lookup or {}
    for index,row in enumerate(rows):
        projected=project_event(row,index=index,data_layer=data_layer)
        if data_layer=='review_supplemental': projected=apply_supplemental_anchor(projected,row,park_lookup=lookup)
        output.append(projected)
    return output

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--skip-write-feeds',action='store_true'); args=parser.parse_args()
    generated_at=utc_now(); staged_rows=extract_events(json.loads(STAGED_PATH.read_text())); supplemental_rows=extract_events(json.loads(SUPPLEMENTAL_PATH.read_text())); park_lookup=load_park_lookup()
    staged_events=project_layer(staged_rows,data_layer='approved_staged'); supplemental_events=project_layer(supplemental_rows,data_layer='review_supplemental',park_lookup=park_lookup)
    staged_env=envelope(staged_events,generated_at_utc=generated_at,next_cursor=None); supp_env=envelope(supplemental_events,generated_at_utc=generated_at,next_cursor=None)
    errors=[]
    if len({e['id'] for e in staged_events})!=len(staged_events): errors.append('duplicate approved ids')
    if len({e['id'] for e in supplemental_events})!=len(supplemental_events): errors.append('duplicate supplemental ids')
    if {e['id'] for e in staged_events}&{e['id'] for e in supplemental_events}: errors.append('approved/supplemental id collision')
    if len(staged_events)!=len(staged_rows): errors.append('approved count mismatch')
    if len(supplemental_events)!=len(supplemental_rows): errors.append('supplemental count mismatch')
    for i,event in enumerate(staged_events[:100]+staged_events[-50:]): validate_event(event,errors,f'staged[{i}]')
    for i,event in enumerate(supplemental_events): validate_event(event,errors,f'supplemental[{i}]')
    report={'schema_version':SCHEMA_VERSION,'generated_at_utc':generated_at,'qa_pass':not errors,'error_count':len(errors),'errors_sample':errors[:40],'staged':{'input_count':len(staged_rows),'output_total':staged_env['total'],'map_ready_count':sum(e['nycif']['coordinate_status']=='map_ready' for e in staged_events)},'supplemental_review':{'input_count':len(supplemental_rows),'output_total':supp_env['total'],'map_ready_count':sum(e['nycif']['coordinate_status']=='map_ready' for e in supplemental_events),'approximate_count':sum(e['nycif']['coordinate_status']=='approximate' for e in supplemental_events),'certified_facility_count':sum(e['nycif'].get('coordinate_precision')=='certified_facility' for e in supplemental_events),'list_only_count':sum(e['nycif']['coordinate_status']=='list_only' for e in supplemental_events),'promotion_allowed_any':any(e['nycif']['promotion_allowed'] for e in supplemental_events),'production_feed_any':any(e['nycif']['production_feed'] for e in supplemental_events)},'safety':{'location_cache_modified':False,'staged_feed_modified':False,'public_map_modified':False,'protected_files_rewritten':False,'promotion_allowed':False}}
    if not args.skip_write_feeds:
        write_repo_json('data/events_schema_v1_staged.json',staged_env); write_repo_json('data/events_schema_v1_supplemental_review.json',supp_env)
    write_repo_json('data/events_schema_v1_validation_report.json',report); print(json.dumps(report,indent=2)); return 0 if report['qa_pass'] else 1
if __name__=='__main__': raise SystemExit(main())
