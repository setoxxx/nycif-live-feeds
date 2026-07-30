#!/usr/bin/env python3
from __future__ import annotations
import json, math, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / 'data' / 'events_discovery_v02_approved.json'
REPORT = ROOT / 'data' / 'reports' / 'stage8_list_only_coordinate_inventory.json'
PROPOSALS = ROOT / 'data' / 'reports' / 'stage8_list_only_coordinate_proposals.json'


def load(path: Path) -> Any:
    with path.open(encoding='utf-8') as f: return json.load(f)

def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True); f.write('\n')

def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        for key in ('events','items','records'):
            if isinstance(value.get(key), list): return [x for x in value[key] if isinstance(x, dict)]
    raise RuntimeError('approved feed must be a list or contain events/items/records')

def num(v: Any) -> float | None:
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def coords(r: dict[str,Any]) -> tuple[float|None,float|None]:
    return num(r.get('lat',r.get('latitude'))), num(r.get('lng',r.get('longitude')))

def valid_nyc(lat: float|None,lng: float|None) -> bool:
    return lat is not None and lng is not None and 40.45 <= lat <= 40.95 and -74.30 <= lng <= -73.65

def norm(v: Any) -> str:
    return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()

def first(r: dict[str,Any], keys: tuple[str,...]) -> str:
    for k in keys:
        v=r.get(k)
        if v not in (None,''): return str(v).strip()
    return ''

def source_id(r: dict[str,Any]) -> str:
    s=r.get('source') if isinstance(r.get('source'),dict) else {}
    return first(r,('source_event_id','event_id','id')) or first(s,('source_event_id','event_id','id'))

def source_name(r: dict[str,Any]) -> str:
    s=r.get('source') if isinstance(r.get('source'),dict) else {}
    return first(r,('source_dataset','source_name','source_slug')) or first(s,('dataset','name','slug'))

def location(r: dict[str,Any]) -> str:
    return first(r,('display_location','location','event_location','address','venue'))

def date(r: dict[str,Any]) -> str:
    return first(r,('date','start_date','event_date','start'))[:10]

def identity(r: dict[str,Any]) -> str:
    sid=source_id(r)
    return '|'.join((norm(source_name(r)),norm(sid),date(r))) if sid else '|'.join((norm(source_name(r)),norm(r.get('title')),date(r),norm(location(r))))

def classify(r: dict[str,Any]) -> str:
    text=' '.join(norm(r.get(k)) for k in ('title','location','display_location','address','venue','description'))
    role=norm(r.get('event_role') or r.get('role'))
    borough=norm(r.get('borough'))
    if any(t in text for t in ('online event','virtual event','zoom','webinar','livestream','live stream')): return 'online_only'
    if role in ('private or reserved activity','private_or_reserved_activity'): return 'private_or_reserved'
    if borough == 'other': return 'outside_nyc_or_other'
    if not location(r): return 'missing_location_text'
    return 'physical_location_unresolved'

def main() -> int:
    events=rows(load(APPROVED))
    map_rows=[]; list_rows=[]
    by_source_id=defaultdict(list); by_location=defaultdict(list)
    for r in events:
        lat,lng=coords(r)
        if valid_nyc(lat,lng):
            map_rows.append(r)
            sid=source_id(r)
            if sid: by_source_id[(norm(source_name(r)),norm(sid))].append((lat,lng,r))
            loc=norm(location(r)); bor=norm(r.get('borough'))
            if loc and bor: by_location[(loc,bor)].append((lat,lng,r))
        else: list_rows.append(r)
    proposals=[]; ledger=[]; reasons=Counter(); methods=Counter()
    for r in list_rows:
        reason=classify(r); proposal=None
        sid=source_id(r); sk=(norm(source_name(r)),norm(sid))
        candidates=by_source_id.get(sk,[]) if sid else []
        method=''
        if candidates:
            unique={(round(x[0],6),round(x[1],6)) for x in candidates}
            if len(unique)==1:
                lat,lng=next(iter(unique)); method='exact_source_event_id_precedent'
                proposal={'lat':lat,'lng':lng,'method':method,'evidence_count':len(candidates)}
        if proposal is None:
            lk=(norm(location(r)),norm(r.get('borough')))
            candidates=by_location.get(lk,[]) if all(lk) else []
            unique={(round(x[0],6),round(x[1],6)) for x in candidates}
            if len(unique)==1:
                lat,lng=next(iter(unique)); method='exact_location_borough_precedent'
                proposal={'lat':lat,'lng':lng,'method':method,'evidence_count':len(candidates)}
        if proposal:
            reason='supported_coordinate_proposal'; methods[method]+=1
            proposals.append({'identity':identity(r),'source':source_name(r),'source_event_id':sid,'title':r.get('title'),'date':date(r),'borough':r.get('borough'),'location':location(r),**proposal})
        reasons[reason]+=1
        ledger.append({'identity':identity(r),'source':source_name(r),'source_event_id':sid,'title':r.get('title'),'date':date(r),'borough':r.get('borough'),'location':location(r),'reason_code':reason,'proposal':proposal})
    now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    report={'artifact_type':'stage8_list_only_coordinate_inventory','schema_version':'1.0.0','generated_at_utc':now,'approved_total':len(events),'map_ready_total':len(map_rows),'list_only_total':len(list_rows),'reason_counts':dict(sorted(reasons.items())),'proposal_method_counts':dict(sorted(methods.items())),'proposal_total':len(proposals),'ledger_total':len(ledger),'equations':{'approved_equals_map_plus_list':len(events)==len(map_rows)+len(list_rows),'list_equals_ledger':len(list_rows)==len(ledger),'proposal_count_matches':len(proposals)==reasons.get('supported_coordinate_proposal',0)},'qa_pass':len(events)==len(map_rows)+len(list_rows)==len(map_rows)+len(ledger)}
    if not report['qa_pass']: raise RuntimeError('Stage 8 inventory equations failed')
    write(REPORT,{**report,'ledger':ledger})
    write(PROPOSALS,{'artifact_type':'stage8_supported_coordinate_proposals','schema_version':'1.0.0','generated_at_utc':now,'promotion_allowed':False,'proposal_total':len(proposals),'proposals':proposals})
    print(json.dumps(report,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
