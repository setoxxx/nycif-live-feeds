#!/usr/bin/env python3
"""Run the fail-closed SHADOW-2 delta after authoritative facility resolvers."""
from __future__ import annotations
import json,os,sys
from collections import Counter
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from enigma.shadow2.read_only_snapshot import ReadOnlySnapshot
from audit_dpr_park_geometry_resolver import build_delta,load_ambiguous_aliases
from nycif.normalize.facility_lookup import canonical_borough,normalize_name,valid_nyc_point
from nycif.normalize.facility_resolvers import resolve_authoritative_facility
from nycif.normalize.facility_resolvers.park_ambiguity_resolver import resolve_borough_qualified_park
from nycif.normalize.park_geometry import load_park_lookup

OUT_JSON=ROOT/'data/shadow2-authoritative-facility-delta.json'; OUT_MD=ROOT/'data/shadow2-authoritative-facility-delta.md'
REC_TYPES={'recreation_center','nature_center','visitor_center','boathouse','field_house'}

def probe_from(item:dict[str,Any]):
    raw=item.get('raw_source_evidence') if isinstance(item.get('raw_source_evidence'),dict) else {}
    return {'id':item.get('id'),'title':item.get('title'),'location':item.get('location'),'display_location':item.get('location'),'borough':item.get('borough') or raw.get('borough'),'event_borough':item.get('borough') or raw.get('borough'),'evidence_tier':'unresolved','source_dataset':item.get('source_dataset'),'source_event_id':item.get('source_event_id')}

def main():
    snapshot=ReadOnlySnapshot(repo_root=ROOT); park_lookup=load_park_lookup(); ambiguous=load_ambiguous_aliases(ROOT/'data/park_centroids_ambiguous_aliases.json')
    baseline=build_delta(snapshot,park_lookup,ambiguous); remaining=baseline['remaining_unresolved_records']
    expected_pre_audit=int(os.environ.get('EXPECTED_PRE_AUDIT','170'))
    if len(remaining)!=expected_pre_audit: raise SystemExit(f'expected pre-audit baseline {expected_pre_audit}, observed {len(remaining)}')
    resolved=[]; unresolved=[]; counts=Counter(); mismatch=[]
    for item in remaining:
        probe=probe_from(item); result=None; resolver=None
        if item.get('failure_reason')=='ambiguous_alias':
            result=resolve_borough_qualified_park(probe)
            if result: resolver='borough_qualified_ambiguity'
        if not result:
            result=resolve_authoritative_facility(probe)
            if result:
                resolver=str(result.get('facility_resolver') or 'facility')
                if resolver=='dpr_structures' and result.get('facility_type') in REC_TYPES:
                    resolver='recreation_centers'
        if not result:
            reason=item.get('failure_reason')
            if reason=='no_park_terminology':
                text=str(item.get('location') or '')
                if not any(term in text.casefold() for term in ('library','school','pool','recreation center','community center','health center')): reason='no_authoritative_dataset_or_vague_location'
                else: reason='facility_name_not_found_in_authoritative_lookup'
            unresolved.append({**item,'final_failure_reason':reason}); continue
        event_borough=canonical_borough(probe.get('borough')); resolved_borough=canonical_borough(result.get('facility_borough') or result.get('park_borough')); warnings=[]
        if not valid_nyc_point(result.get('latitude'),result.get('longitude')): warnings.append('coordinate_outside_nyc')
        if not event_borough or not resolved_borough or event_borough!=resolved_borough: warnings.append('borough_mismatch_or_missing')
        if result.get('coordinate_status')!='approximate' or result.get('promotion_allowed') is not False: warnings.append('unsafe_status')
        if result.get('coordinate_precision')=='certified_facility':
            matched_alias=result.get('facility_matched_alias')
            if not matched_alias or matched_alias!=normalize_name(result.get('facility_query_name')):
                warnings.append('exact_alias_evidence_missing')
        record={**item,**result,'resolver':resolver,'event_borough':event_borough,'resolved_borough':resolved_borough,'verification_warnings':warnings,'verification_state':'verified' if not warnings else 'mismatch'}
        resolved.append(record); counts[resolver]+=1
        if warnings: mismatch.append(record)
    remainder_counts=Counter(item['final_failure_reason'] for item in unresolved)
    report={'baseline_unresolved':expected_pre_audit,'resolved_by_dpr_structures':counts['dpr_structures'],'resolved_by_libraries':counts['libraries'],'resolved_by_schools':counts['schools'],'resolved_by_pools':counts['pools'],'resolved_by_recreation_centers':counts['recreation_centers'],'resolved_by_borough_qualified_ambiguity':counts['borough_qualified_ambiguity'],'resolved_total':len(resolved),'remain_unresolved':len(unresolved),'false_match_count':len(mismatch),'resolver_distribution':dict(sorted(counts.items())),'remainder_distribution':dict(sorted(remainder_counts.items())),'resolved_records':resolved,'remaining_records':unresolved,'safety':{'all_approximate':all(r.get('coordinate_status')=='approximate' for r in resolved),'promotion_allowed_any':any(r.get('promotion_allowed') is True for r in resolved),'map_ready_any':any(r.get('coordinate_status')=='map_ready' for r in resolved),'workflow_write_required':False}}
    OUT_JSON.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    lines=['# SHADOW-2 Authoritative Facility Delta','',f'- Baseline unresolved: **{expected_pre_audit}**',f'- Resolved total: **{len(resolved)}**',f'- Remain unresolved: **{len(unresolved)}**',f'- Structural false-match warnings: **{len(mismatch)}**','', '## Resolver delta']+[f'- {k}: {v}' for k,v in sorted(counts.items())]+['','## True remainder']+[f'- {k}: {v}' for k,v in sorted(remainder_counts.items())]
    OUT_MD.write_text('\n'.join(lines)+'\n')
    compact={k:v for k,v in report.items() if k not in {'resolved_records','remaining_records'}}
    compact['warning_records']=[{'id':r.get('id'),'location':r.get('location'),'resolver':r.get('resolver'),'warnings':r.get('verification_warnings')} for r in mismatch]
    print(json.dumps(compact,indent=2)); return 0 if not mismatch and report['safety']['all_approximate'] and not report['safety']['promotion_allowed_any'] else 1
if __name__=='__main__': raise SystemExit(main())
